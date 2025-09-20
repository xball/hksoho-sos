import frappe
from frappe import _

@frappe.whitelist()
def get_po_items(po_name):
    """回傳指定 Purchase Order 的所有明細項目"""
    if not po_name:
        frappe.throw(_("請提供有效的採購訂單編號"))

    try:
        items = frappe.get_all(
            "Purchase Order Item",
            filters={"parent": po_name},
            fields=["name", "line", "article_number", "article_name", "confirmed_qty", "ctns_on_pallet", "carton_cbm", "carton_gross_kg", "unit_price"],
            order_by="line asc"
        )

        if not items:
            frappe.msgprint({
                title: _("無數據"),
                message: _("未找到指定的採購訂單項目。"),
                indicator: "orange"
            })

        return items
    except frappe.PermissionError:
        frappe.throw(_("您沒有足夠的權限來訪問採購訂單項目。請聯繫您的管理員以獲取訪問權限。"), frappe.PermissionError)
    except Exception as e:
        frappe.log_error(f"Error fetching PO items for {po_name}: {str(e)}")
        frappe.throw(_("無法獲取採購訂單項目，請稍後重試。錯誤：{0}").format(str(e)))