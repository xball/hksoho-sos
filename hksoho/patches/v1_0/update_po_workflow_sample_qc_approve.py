# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Allow Sample POs to QC Approve without line Pass/Fail.

Sample still goes Ready to QC (inspection path unchanged).
Non-Sample types still require at least one line with qc_update_status == Pass.
"""

import frappe

WORKFLOW_NAME = "PO-Workflow"
STATE = "Ready to QC"
ACTION = "QC Approve"
NEW_CONDITION = (
	'doc.order_type == "Sample" or '
	'[item for item in doc.po_items if item.qc_update_status == "Pass"]'
)


def execute():
	if not frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.log_error(
			message=f"Workflow {WORKFLOW_NAME} not found; skipped Sample QC Approve update",
			title="update_po_workflow_sample_qc_approve",
		)
		return

	wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
	updated = False
	for transition in wf.transitions:
		if transition.state == STATE and transition.action == ACTION:
			current = (transition.condition or "").strip()
			if current == NEW_CONDITION.strip():
				return
			transition.condition = NEW_CONDITION
			updated = True
			break

	if not updated:
		frappe.log_error(
			message=f"No transition {STATE} --[{ACTION}]--> found on {WORKFLOW_NAME}",
			title="update_po_workflow_sample_qc_approve",
		)
		return

	wf.save(ignore_permissions=True)
	frappe.db.commit()
