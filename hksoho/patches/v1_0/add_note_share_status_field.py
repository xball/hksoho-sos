# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Add the hidden ``Note.share_status`` field used by the list view pill.

The field is a real column (Custom Field) rather than a computed value so that
the list view's indicator pill stays click-to-filterable: frappe renders the
third element of ``get_indicator()`` as a ``data-filter`` and DatabaseQuery
rejects sub-queries in ``fields``, so a stored value is required.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	create_custom_field(
		"Note",
		{
			"fieldname": "share_status",
			"label": "Share Status",
			"fieldtype": "Select",
			"options": "Private\nShared\nPublic",
			"default": "Private",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"report_hide": 1,
			"description": "Derived from DocShare: Private / Shared / Public.",
		},
	)

	frappe.clear_cache(doctype="Note")

	from hksoho.byrydens.note_permissions import backfill_share_status

	backfill_share_status()
