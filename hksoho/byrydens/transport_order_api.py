import frappe
from frappe import _
import json

@frappe.whitelist()
def get_po_items(po_name, filters=None):
    """Return all items for the specified Purchase Order where workflow_state is 'Ready to Ship' and qty > 0"""
    if not po_name:
        frappe.throw("Please provide a valid Purchase Order number")

    try:
        # Check if the Purchase Order has workflow_state = 'Ready to Ship'
        po = frappe.get_doc("Purchase Order", po_name)
        if po.workflow_state != "Ready to Ship":
            frappe.msgprint({
                "title": "No Data",
                "message": f"The Purchase Order {po_name} does not have workflow_state 'Ready to Ship'.",
                "indicator": "orange"
            })
            return []

        # Initialize filters for Purchase Order Item
        filters = filters or {}
        filters['parent'] = po_name

        # Fetch items with necessary fields
        items = frappe.get_all(
            "Purchase Order Item",
            filters=filters,
            fields=["name", "line", "article_number", "article_name", "booked_qty", "delivery_qty", "ctns_on_pallet", "carton_cbm", "carton_gross_kg", "unit_price"],
            order_by="line asc"
        )

        # Filter items where qty = booked_qty - delivery_qty > 0
        filtered_items = [
            item for item in items
            if (item.get('booked_qty', 0) - item.get('delivery_qty', 0)) > 0
        ]

        if not filtered_items:
            frappe.msgprint({
                "title": "No Data",
                "message": "No items found for the specified Purchase Order with qty > 0.",
                "indicator": "orange"
            })

        return filtered_items
    except frappe.DoesNotExistError:
        frappe.throw(f"Purchase Order {po_name} does not exist.")
    except frappe.PermissionError:
        frappe.throw("You do not have sufficient permissions to access Purchase Order items. Please contact your administrator for access.", frappe.PermissionError)
    except Exception as e:
        frappe.log_error(f"Error fetching PO items for {po_name}: {str(e)}")
        frappe.throw(f"Failed to fetch Purchase Order items. Please try again later. Error: {str(e)}")
        
        
import frappe
from frappe import _
import json

@frappe.whitelist()
def update_to_line_invoice(to_name, po_number, invoice_data):
    """
    Update invoice details for Transport Order Line items matching the given po_number and save the Transport Order.

    Args:
        to_name (str): Name of the Transport Order
        po_number (str): Selected Purchase Order number
        invoice_data (str or dict): Dictionary or JSON string containing invoice details, e.g.:
            {
                "invoice_received": 1,
                "invoice_no": "INV-20251003",
                "invoice_currency": "USD",
                "invoice_date": "2025-10-03",
                "invoice_due_date": "2025-11-03",
                "invoice_paid": 0,
                "exchange_rate_to_sek": 10.5
            }
    Returns:
        dict: Result message indicating success or failure
    """
    try:
        # Parse invoice_data if it's a string
        if isinstance(invoice_data, str):
            invoice_data = json.loads(invoice_data)
        elif not isinstance(invoice_data, dict):
            frappe.throw(_("Invalid invoice_data format. Expected a dictionary or JSON string."))

        # Get Transport Order
        to_doc = frappe.get_doc("Transport Order", to_name)

        # Validate po_line links
        invalid_lines = []
        for item in to_doc.items:
            if item.po_number == po_number and item.po_line:
                if not frappe.db.exists("Purchase Order Item", item.po_line):
                    invalid_lines.append(f"Row #{item.idx}: PO Line: {item.po_line}")

        if invalid_lines:
            frappe.throw(_("Could not find the following PO Line references: {0}").format(", ".join(invalid_lines)))

        # Validate invoice data
        if invoice_data.get("invoice_received") and invoice_data.get("invoice_date") and invoice_data.get("invoice_due_date"):
            if invoice_data["invoice_due_date"] < invoice_data["invoice_date"]:
                frappe.throw(_("Invoice Due Date cannot be earlier than Invoice Date."))

        updated = False
        # Update Transport Order Line
        for item in to_doc.items:
            if item.po_number == po_number:
                item.invoice_received = invoice_data.get("invoice_received", 0)
                if item.invoice_received:
                    item.invoice_no = invoice_data.get("invoice_no")
                    item.invoice_currency = invoice_data.get("invoice_currency")
                    item.invoice_date = invoice_data.get("invoice_date")
                    item.invoice_due_date = invoice_data.get("invoice_due_date")
                    item.invoice_paid = invoice_data.get("invoice_paid", 0)
                    item.exchange_rate_to_sek = invoice_data.get("exchange_rate_to_sek")
                else:
                    item.invoice_no = None
                    item.invoice_currency = None
                    item.invoice_date = None
                    item.invoice_due_date = None
                    item.invoice_paid = 0
                    item.exchange_rate_to_sek = None
                updated = True

        if not updated:
            frappe.throw(_("No items found matching the selected Purchase Order: {0}").format(po_number))

        # Save Transport Order
        to_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "success",
            "message": "Invoice details updated and form saved successfully!"
        }

    except Exception as e:
        # Truncate error message to avoid CharacterLengthExceededError
        error_message = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        frappe.log_error(f"Failed to update Transport Order Line: {error_message}", "Update TO Line Invoice")
        return {
            "status": "error",
            "message": f"Failed to update invoice details: {error_message}"
        }
        


@frappe.whitelist()
def update_vessel_dates(vessel_name, cfs_close=None, etd_date=None, eta_date=None, dest_port_free_days=0, to_name=None):
    vessel = frappe.get_doc("Vessels Time Table", vessel_name)
    
    if cfs_close: 
        vessel.cfs_close = cfs_close
    if etd_date:  
        vessel.etd_date = etd_date
    if eta_date:  
        vessel.eta_date = eta_date
    vessel.dest_port_free_days = int(dest_port_free_days)
    
    vessel.save(ignore_permissions=True)

# 2. 更新 Transport Order → 改用 set_value 強制寫入（完全無視 workflow 凍結）
    if to_name:
        updates = {}
        if cfs_close:          
            updates["cfs_close"] = cfs_close
        if etd_date:           
            updates["etd_date"] = etd_date
            #updates["booked_etd"] = etd_date
        if eta_date:           
            updates["eta_date"] = eta_date
            updates["dest_port_free_days"] = int(dest_port_free_days)

        frappe.db.set_value("Transport Order", to_name, updates)

    frappe.db.commit()
    return {"status": "success"}
    
    # if to_name:
    #     to_doc = frappe.get_doc("Transport Order", to_name)
    #     if cfs_close: to_doc.cfs_close = cfs_close
    #     if etd_date:
    #         to_doc.etd_date = etd_date
    #         #to_doc.booked_etd = etd_date          # 同步 Booked ETD
    #     if eta_date: to_doc.eta_date = eta_date
    #     to_doc.dest_port_free_days = int(dest_port_free_days)
    #     to_doc.save(ignore_permissions=True)
    
    # frappe.db.commit()
    # return {"status": "success"}