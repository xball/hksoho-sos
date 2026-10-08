# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Rename the Product Sheet free-text option from 空白自填 to Others."""

import frappe


def execute():
	for fieldname in ("packing_method", "hangtag"):
		if not frappe.db.has_column("Product Sheet", fieldname):
			continue
		frappe.db.sql(
			f"""
			update `tabProduct Sheet`
			set `{fieldname}` = 'Others'
			where `{fieldname}` = '空白自填'
			"""
		)
