import frappe

@frappe.whitelist()
def get_po_items(po_name, filters=None):
    """Return all items for the specified Purchase Order where workflow_state is 'Booked QTY' and qty > 0"""
    if not po_name:
        frappe.throw("Please provide a valid Purchase Order number")

    try:
        # Check if the Purchase Order has workflow_state = 'Booked QTY'
        po = frappe.get_doc("Purchase Order", po_name)
        if po.workflow_state != "Booked QTY":
            frappe.msgprint({
                "title": "No Data",
                "message": f"The Purchase Order {po_name} does not have workflow_state 'Booked QTY'.",
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