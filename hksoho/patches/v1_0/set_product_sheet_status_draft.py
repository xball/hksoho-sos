# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Set empty Product Sheet status to Draft after the status field is added."""

import frappe


def execute():
	if not frappe.db.has_column("Product Sheet", "status"):
		return
	frappe.db.sql(
		"""
		update `tabProduct Sheet`
		set `status` = 'Draft'
		where `status` is null or `status` = ''
		"""
	)
