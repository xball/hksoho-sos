import frappe
from frappe.model.document import Document

@frappe.whitelist()
def get_suppliers():
    return frappe.get_list('Partner', filters={'partner_type': 'Supplier', 'status': 'Active'}, fields=['name', 'partner_name'])

@frappe.whitelist()
def get_sales_orders(supplier):
    return frappe.get_list('Purchase Order', filters={'supplier': supplier}, fields=['name'])

@frappe.whitelist()
def get_order_items(order):
    return frappe.get_doc('Purchase Order', order).order_items

@frappe.whitelist()
def get_inspection_items(template_name):
    template = frappe.get_doc('Inspection Template', template_name)
    return template.inspection_items

@frappe.whitelist()
def get_po_items(po_name):
    """回傳指定 Purchase Order2 的所有明細"""
    if not po_name:
        frappe.throw("請提供有效的採購訂單編號")
    
    items = frappe.get_all(
        "Purchase Order Item2",
        filters={"parent": po_name},
        fields=["name", "line",  "requested_qty", "article_number", "confirmed_qty"],
        order_by="line asc"
    )
    
    return items