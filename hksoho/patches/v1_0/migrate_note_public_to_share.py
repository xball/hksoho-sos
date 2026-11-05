# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Convert legacy ``Note.public = 1`` notes into an "Everyone" DocShare row.

``public`` no longer drives visibility on its own (the Share dialog does), but
it is still honoured as a backwards-compatible fallback in
``note_permissions.has_permission``. Converting the flag keeps the Share dialog
authoritative: the owner can then revoke Everyone access, which would not have
been possible with the flag.

The ``public`` column itself is left in place and only reset to 0.
"""

import frappe


def execute():
	if not frappe.db.has_column("Note", "share_status"):
		# The status field patch did not run; nothing to migrate.
		return

	public_notes = frappe.get_all("Note", filters={"public": 1}, pluck="name", limit=0)

	for name in public_notes:
		if not frappe.db.exists(
			"DocShare", {"share_doctype": "Note", "share_name": name, "everyone": 1}
		):
			share = frappe.new_doc("DocShare")
			share.update(
				{
					"share_doctype": "Note",
					"share_name": name,
					"everyone": 1,
					"read": 1,
					"write": 0,
					"submit": 0,
					"share": 0,
					"notify_by_email": 0,
				}
			)
			share.flags.ignore_permissions = True
			share.flags.ignore_share_permission = True
			share.insert()

		frappe.db.set_value("Note", name, "public", 0, update_modified=False)

	from hksoho.byrydens.note_permissions import backfill_share_status

	backfill_share_status()
