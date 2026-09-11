# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.model.document import Document


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}


def get_file_type_from_url(file_url: str | None) -> str:
	if not file_url:
		return ""
	ext = os.path.splitext(file_url.split("?")[0])[1].lower()
	if ext in PDF_EXTENSIONS:
		return "PDF"
	if ext in IMAGE_EXTENSIONS:
		return ext.lstrip(".").upper()
	return ext.lstrip(".").upper() if ext else ""


class CustomerQuotation(Document):
	pass


@frappe.whitelist()
def get_article_master_files(article_master: str) -> list[dict]:
	"""Return printable files from linked Article Master (files table + product_image)."""
	if not article_master:
		frappe.throw(frappe._("Article Master is required"))

	if not frappe.db.exists("Article Master", article_master):
		frappe.throw(frappe._("Article Master {0} not found").format(article_master))

	am = frappe.get_doc("Article Master", article_master)
	files: list[dict] = []

	if am.product_image:
		files.append(
			{
				"description": "Product image",
				"attach_file": am.product_image,
				"file_type": get_file_type_from_url(am.product_image),
				"print": 1,
			}
		)

	for row in am.get("files") or []:
		if not row.attach_file:
			continue
		files.append(
			{
				"description": row.description or "",
				"attach_file": row.attach_file,
				"file_type": get_file_type_from_url(row.attach_file),
				"print": 1,
			}
		)

	return files
