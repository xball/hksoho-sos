# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Copy the single RoHS link before that column is replaced by a child table."""

import frappe

STASH = "Product Sheet RoHS Migrate"


def execute():
	if not frappe.db.table_exists("Product Sheet"):
		return
	if not frappe.db.has_column("Product Sheet", "rohs_document_relevant_code"):
		return

	frappe.db.sql_ddl(f"drop table if exists `tab{STASH}`")
	frappe.db.sql_ddl(
		f"""
		create table `tab{STASH}` (
			parent varchar(140),
			rohs_document_relevant_code varchar(140)
		)
		"""
	)
	frappe.db.sql(
		f"""
		insert into `tab{STASH}` (parent, rohs_document_relevant_code)
		select name, rohs_document_relevant_code
		from `tabProduct Sheet`
		where ifnull(rohs_document_relevant_code, '') != ''
		"""
	)
