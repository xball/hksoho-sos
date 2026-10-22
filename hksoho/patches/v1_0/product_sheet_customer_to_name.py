# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Replace Product Sheet customer Partner IDs with partner names after Customer becomes Data."""

import frappe


def execute():
	if not frappe.db.has_column("Product Sheet", "customer"):
		return
	frappe.db.sql(
		"""
		update `tabProduct Sheet` ps
		inner join `tabPartner` p on p.name = ps.customer
		set ps.customer = p.partner_name
		where ifnull(p.partner_name, '') != ''
		"""
	)
