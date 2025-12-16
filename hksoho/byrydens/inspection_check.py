import frappe
from frappe.utils import getdate, today

def execute():
    current_date = getdate()  # 今天日期（date 物件）

    frappe.log_error(
        title="Inspection Event Scheduler",
        message=f"Job started, current_date={current_date}"
    )

    # 1. 找出所有 Open 的 Inspection Event
    events = frappe.get_all(
        "Inspection Event",
        filters={"status": "Open"},
        fields=["name", "starts_on", "supplier"]
    )

    if not events:
        frappe.log_error(
            title="Inspection Event Scheduler",
            message="No open Inspection Event found"
        )
        return

    frappe.log_error(
        title="Inspection Event Scheduler",
        message=f"Found {len(events)} open Inspection Event(s): {[e.name for e in events]}"
    )

    for ev in events:
        ev_doc = frappe.get_doc("Inspection Event", ev.name)

        # 使用 starts_on 的日期，沒有就用今天
        event_date = getdate(ev_doc.starts_on) if ev_doc.starts_on else current_date

        frappe.log_error(
            title="Inspection Event Scheduler",
            message=f"Processing Event {ev_doc.name}, supplier={ev_doc.supplier}, "
                    f"starts_on={ev_doc.starts_on}, event_date={event_date}"
        )

        if not ev_doc.po_items:
            frappe.log_error(
                title="Inspection Event Scheduler",
                message=f"Event {ev_doc.name} has no PO Items"
            )
            continue

        all_lines_completed = True

        for line in ev_doc.po_items:
            frappe.log_error(
                title="Inspection Event Scheduler",
                message=f"  Line name={line.name}, po_number={line.po_number}, "
                        f"po_item={line.po_item}, status={line.status}"
            )

            # 已經 Completed 的就略過
            if line.status == "Completed":
                continue

            po_number = line.po_number
            po_line = line.po_item

            if not po_number or not po_line:
                all_lines_completed = False
                frappe.log_error(
                    title="Inspection Event Scheduler",
                    message=f"  Line {line.name} missing po_number or po_item, skip"
                )
                continue

            # 2. 找對應 Inspection（同一天）
            inspections = frappe.get_all(
                "Inspection",
                filters={
                    "supplier": ev_doc.supplier,
                    "purchase_order": po_number,
                    "purchase_order_line": po_line,
                    "inspection_date": event_date,
                    # 如需更嚴謹，可加:
                    # "result": ["!=", "NA"],
                    # "docstatus": 1,
                },
                fields=["name", "result"]
            )

            if inspections:
                line.status = "Completed"
                frappe.log_error(
                    title="Inspection Event Scheduler",
                    message=f"  Line {line.name} marked Completed, "
                            f"found Inspections: {[i.name for i in inspections]}"
                )
            else:
                all_lines_completed = False
                frappe.log_error(
                    title="Inspection Event Scheduler",
                    message=f"  Line {line.name} still Scheduled, "
                            f"no Inspection found on {event_date}"
                )

        # 儲存子表狀態
        ev_doc.save(ignore_permissions=True)

        # 3. 如果所有行都 Completed，更新 Event 狀態
        if all_lines_completed and ev_doc.status != "Completed":
            old_status = ev_doc.status
            ev_doc.status = "Completed"
            ev_doc.save(ignore_permissions=True)
            frappe.log_error(
                title="Inspection Event Scheduler",
                message=f"Event {ev_doc.name} status changed {old_status} -> Completed"
            )

    frappe.db.commit()
    frappe.log_error(
        title="Inspection Event Scheduler",
        message="Job finished"
    )
