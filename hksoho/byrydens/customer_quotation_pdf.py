# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Append selected Customer Quotation print files after Quo-Report PDF."""

from __future__ import annotations

import io
import os
from typing import Literal

import frappe
from frappe.utils.print_format import download_pdf as _download_pdf
from pypdf import PdfReader, PdfWriter

from hksoho.byrydens.doctype.customer_quotation.customer_quotation import (
	IMAGE_EXTENSIONS,
	PDF_EXTENSIONS,
	get_file_type_from_url,
)

QUO_REPORT_FORMAT = "Quo-Report"


@frappe.whitelist(allow_guest=True)
def download_pdf(
	doctype: str,
	name: str,
	format=None,
	doc=None,
	no_letterhead=0,
	language=None,
	letterhead=None,
	pdf_generator: Literal["wkhtmltopdf", "chrome"] | None = None,
):
	_download_pdf(
		doctype=doctype,
		name=name,
		format=format,
		doc=doc,
		no_letterhead=no_letterhead,
		language=language,
		letterhead=letterhead,
		pdf_generator=pdf_generator,
	)

	if doctype != "Customer Quotation" or format != QUO_REPORT_FORMAT:
		return

	base_pdf = frappe.local.response.get("filecontent")
	if not base_pdf:
		return

	try:
		merged = append_print_files(name, base_pdf)
		if merged:
			frappe.local.response.filecontent = merged
	except Exception:
		frappe.log_error(
			title=f"Quo-Report attachment merge failed for {name}",
			message=frappe.get_traceback(),
		)


def append_print_files(quotation_name: str, base_pdf: bytes) -> bytes | None:
	doc = frappe.get_doc("Customer Quotation", quotation_name)
	rows = [
		row
		for row in (doc.get("print_files") or [])
		if cint_print(row.print) and row.attach_file
	]
	if not rows:
		return None

	writer = PdfWriter()
	writer.append_pages_from_reader(PdfReader(io.BytesIO(base_pdf)))

	appended = 0
	for row in rows:
		try:
			page_pdf = file_url_to_pdf_bytes(row.attach_file)
			if not page_pdf:
				frappe.logger("customer_quotation_pdf").warning(
					f"Skipped unsupported/missing file on {quotation_name}: {row.attach_file}"
				)
				continue
			writer.append_pages_from_reader(PdfReader(io.BytesIO(page_pdf)))
			appended += 1
		except Exception:
			frappe.logger("customer_quotation_pdf").warning(
				f"Failed to append {row.attach_file} to {quotation_name}: {frappe.get_traceback()}"
			)

	if not appended:
		return None

	out = io.BytesIO()
	writer.write(out)
	return out.getvalue()


def cint_print(value) -> bool:
	return int(value or 0) == 1


def file_url_to_pdf_bytes(file_url: str) -> bytes | None:
	file_type = get_file_type_from_url(file_url)
	ext = os.path.splitext(file_url.split("?")[0])[1].lower()

	file_path = get_local_file_path(file_url)
	if not file_path or not os.path.exists(file_path):
		return None

	if ext in PDF_EXTENSIONS or file_type == "PDF":
		with open(file_path, "rb") as f:
			return f.read()

	if ext in IMAGE_EXTENSIONS:
		return image_to_pdf_bytes(file_path)

	return None


def get_local_file_path(file_url: str) -> str | None:
	"""Resolve a Frappe file_url to a site-local filesystem path."""
	if not file_url:
		return None

	# Prefer File doctype lookup
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if file_name:
		file_doc = frappe.get_doc("File", file_name)
		try:
			return file_doc.get_full_path()
		except Exception:
			pass

	# Fallback: map /private/files/... or /files/... under site path
	if file_url.startswith("/private/files/"):
		return frappe.get_site_path("private", "files", file_url[len("/private/files/") :])
	if file_url.startswith("/files/"):
		return frappe.get_site_path("public", "files", file_url[len("/files/") :])
	if file_url.startswith("private/files/"):
		return frappe.get_site_path(file_url)
	if file_url.startswith("files/"):
		return frappe.get_site_path("public", file_url)

	return None


def image_to_pdf_bytes(image_path: str) -> bytes:
	from PIL import Image

	with Image.open(image_path) as img:
		# PDF encoder expects RGB
		if img.mode in ("RGBA", "P", "LA"):
			background = Image.new("RGB", img.size, (255, 255, 255))
			if img.mode == "P":
				img = img.convert("RGBA")
			background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
			img = background
		elif img.mode != "RGB":
			img = img.convert("RGB")

		buf = io.BytesIO()
		img.save(buf, format="PDF", resolution=150.0)
		return buf.getvalue()
