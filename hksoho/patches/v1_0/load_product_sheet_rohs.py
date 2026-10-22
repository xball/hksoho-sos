# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Move stashed RoHS codes onto the Product Sheet child table."""

import frappe

STASH = "Product Sheet RoHS Migrate"


def execute():
	if not frappe.db.table_exists(STASH):
		return
	if not frappe.db.table_exists("Product Sheet RoHS"):
		return

	rows = frappe.db.sql(
		f"""
		select parent, rohs_document_relevant_code
		from `tab{STASH}`
		where ifnull(rohs_document_relevant_code, '') != ''
		""",
		as_dict=True,
	)
	for row in rows:
		if not frappe.db.exists("Product Sheet", row.parent):
			continue
		already = frappe.db.exists(
			"Product Sheet RoHS",
			{
				"parent": row.parent,
				"parenttype": "Product Sheet",
				"parentfield": "rohs",
				"rohs_document_relevant_code": row.rohs_document_relevant_code,
			},
		)
		if already:
			continue
		idx = frappe.db.sql(
			"""
			select ifnull(max(idx), 0) + 1
			from `tabProduct Sheet RoHS`
			where parent=%s and parenttype='Product Sheet' and parentfield='rohs'
			""",
			row.parent,
		)[0][0]
		child = frappe.new_doc("Product Sheet RoHS")
		child.parent = row.parent
		child.parenttype = "Product Sheet"
		child.parentfield = "rohs"
		child.idx = idx
		child.rohs_document_relevant_code = row.rohs_document_relevant_code
		child.name = frappe.generate_hash(length=10)
		child.db_insert()

	frappe.db.sql_ddl(f"drop table if exists `tab{STASH}`")
