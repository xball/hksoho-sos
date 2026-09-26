# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Auto-share documents when assigned (Read + Write)."""

import frappe
import frappe.share

# DocTypes that should be shared Read+Write when assigned via ToDo
SHARE_ON_ASSIGN_DOCTYPES = ("Product Sheet",)


def share_on_todo_assign(doc, method=None):
	"""On ToDo insert: share the linked document with the assignee (Read + Write)."""
	if not doc.allocated_to or not doc.reference_type or not doc.reference_name:
		return

	if doc.reference_type not in SHARE_ON_ASSIGN_DOCTYPES:
		return

	if doc.status and doc.status != "Open":
		return

	if frappe.get_system_settings("disable_document_sharing"):
		return

	if not frappe.db.exists(doc.reference_type, doc.reference_name):
		return

	# Share with Read + Write. notify=0 — assignment already notifies the user.
	frappe.share.add(
		doc.reference_type,
		doc.reference_name,
		doc.allocated_to,
		read=1,
		write=1,
		notify=0,
	)
