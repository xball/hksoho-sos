# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class ProductSheet(Document):
	def validate(self):
		self.validate_unique_rohs()
		self.calculate_qty_20()

	def calculate_qty_20(self):
		volume = flt(self.outer_carton_volume_m3)
		qty = cint(self.quantity_outer_carton)
		if volume and qty:
			self.qty_20 = round(28 / (volume * qty))
		else:
			self.qty_20 = 0

	def validate_unique_rohs(self):
		seen = {}
		for row in self.get("rohs") or []:
			code = (row.rohs_document_relevant_code or "").strip()
			if not code:
				continue
			if code in seen:
				frappe.throw(
					_("RoHS Document Relevant Code {0} is duplicated in rows {1} and {2}").format(
						code, seen[code], row.idx
					)
				)
			seen[code] = row.idx


def fit_print_image(file_url, max_width_mm=43.0, max_height_mm=35.0):
	"""Size an image to fit a print box without stretching."""
	fallback = {"width_mm": max_width_mm, "height_mm": max_height_mm}
	if not file_url:
		return fallback

	try:
		from PIL import Image

		path = _print_image_path(file_url)
		if not path:
			return fallback
		with Image.open(path) as img:
			px_w, px_h = img.size
		if not px_w or not px_h:
			return fallback
		aspect = float(px_w) / float(px_h)
		box_aspect = max_width_mm / max_height_mm
		if box_aspect > aspect:
			height_mm = max_height_mm
			width_mm = max_height_mm * aspect
		else:
			width_mm = max_width_mm
			height_mm = max_width_mm / aspect
		return {"width_mm": round(width_mm, 2), "height_mm": round(height_mm, 2)}
	except Exception:
		return fallback


def _print_image_path(file_url):
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if file_name:
		try:
			return frappe.get_doc("File", file_name).get_full_path()
		except Exception:
			pass
	name = file_url.split("?")[0].split("/")[-1]
	if "/private/files/" in file_url:
		return frappe.get_site_path("private", "files", name)
	if "/files/" in file_url:
		return frappe.get_site_path("public", "files", name)
	return None
