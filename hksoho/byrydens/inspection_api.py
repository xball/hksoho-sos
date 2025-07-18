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