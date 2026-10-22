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
