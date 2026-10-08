# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Keep Product Sheet packing text that is not in the new option list.

Select fields drop a stored value that is no longer an option when the form
opens. Move those old combined descriptions into the custom packing field.
"""

import frappe

PRESETS = {
	"Light Box",
	"Standard Box",
	"Grand Box",
	"Color Box",
	"Mailbox",
	"Shrink pack",
	"OPP",
	"Others",
}


def execute():
	if not frappe.db.has_column("Product Sheet", "packing_method_custom"):
		return

	rows = frappe.db.sql(
		"""
		select name, packing_method
		from `tabProduct Sheet`
		where ifnull(packing_method, '') != ''
		""",
		as_dict=True,
	)
	for row in rows:
		value = (row.packing_method or "").strip()
		if value in PRESETS:
			continue
		if value == "None":
			frappe.db.set_value(
				"Product Sheet", row.name, "packing_method", "", update_modified=False
			)
			continue
		frappe.db.set_value(
			"Product Sheet",
			row.name,
			{"packing_method": "Others", "packing_method_custom": value},
			update_modified=False,
		)
