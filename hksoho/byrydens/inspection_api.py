import frappe
from frappe import _
from frappe.model.document import Document
import json

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

@frappe.whitelist()
def get_po_items_qcstatus(po_name):
    """
    獲取指定採購訂單的項目，僅返回 qc_update_status 不等於 'Pass' 的項目。
    
    Args:
        po_name (str): 採購訂單名稱
    Returns:
        list: 包含項目詳細信息的列表
    """
    if not po_name:
        frappe.throw(_("請提供有效的採購訂單編號"))
    items = frappe.get_all(
        "Purchase Order Item2",
        filters={"parent": po_name, "qc_update_status": ["!=", "Pass"]},
        fields=["name", "line", "requested_qty", "article_number", "article_name", "confirmed_qty"],
        order_by="line asc"
    )
    if not items and not frappe.has_permission("Purchase Order2", "read", po_name):
        frappe.throw(
            _("You do not have enough permissions to access this resource. Please contact your manager to get access."),
            frappe.PermissionError
        )
    return items

@frappe.whitelist()
def add_po_items_to_inspection_event(inspection_event_name, selected_items):
    """
    將選中的 Purchase Order Item2 添加到 Inspection Event 的 po_items 表（Inspection Line），
    使用 po_number 和 po_item.line 檢查重複，跳過已存在項目並提示。
    
    Args:
        inspection_event_name (str): Inspection Event 的名稱
        selected_items (str or list): 選中的 Purchase Order Item2 的 name 列表
    Returns:
        dict: 包含操作狀態和訊息
    """
    # 檢查用戶是否有寫入 Inspection Event 的權限
    if not frappe.has_permission("Inspection Event", "write", inspection_event_name):
        frappe.throw(
            _("You do not have enough permissions to access this resource. Please contact your manager to get access."),
            frappe.PermissionError
        )

    # 獲取 Inspection Event 文檔
    inspection_event = frappe.get_doc("Inspection Event", inspection_event_name)
    
    # 處理 selected_items（可能是 JSON 字符串）
    if isinstance(selected_items, str):
        try:
            selected_items = json.loads(selected_items)
        except json.JSONDecodeError:
            frappe.throw(_("無效的項目選擇格式。"))

    # 驗證 selected_items 是否為非空列表
    if not selected_items or not isinstance(selected_items, list):
        frappe.throw(_("無有效的項目被選擇。"))

    # 獲取選中的項目數據
    items = frappe.get_all(
        "Purchase Order Item2",
        filters={"name": ["in", selected_items]},
        fields=["name", "line", "requested_qty", "article_number", "article_name", "confirmed_qty", "parent"]
    )

    if not items:
        frappe.throw(_("無有效的項目被選擇。"))

    # 獲取當前 po_items 表中的 po_number 和 po_item.line 組合，用於檢查重複
    existing_items = set()
    for row in inspection_event.po_items:
        if row.po_number and row.po_item:
            po_item = frappe.get_doc("Purchase Order Item2", row.po_item)
            if po_item.line is not None:
                existing_items.add((row.po_number, po_item.line))

    added_count = 0
    skipped_items = []
    # 假設第一個項目的 supplier 適用於所有項目（因為它們來自同一個 PO）
    supplier = None
    if items:
        po = frappe.get_doc("Purchase Order2", items[0].parent)
        supplier = po.supplier if po.supplier else None

    # 將項目添加到 po_items 表，跳過已存在的項目
    for item in items:
        if (item.parent, item.line) not in existing_items:
            inspection_event.append("po_items", {
                "po_item": item.name,  # Link 到 Purchase Order Item2
                "po_number": item.parent,  # 設置 PO 號碼
                "article_number": item.article_number,  # Link 到 Product
                "article_name": item.article_name,  # 設置 Article Name
                "confirmed_qty": item.confirmed_qty  # 設置 Confirmed QTY
            })
            added_count += 1
        else:
            skipped_items.append(f"PO {item.parent}, Line {item.line}")

    # 構建回應訊息
    if added_count == 0:
        message = _("所有選擇的項目已存在於表中，無新項目添加。")
        if skipped_items:
            message += "\n" + _("跳過的項目：") + "\n" + "\n".join(skipped_items)
        frappe.msgprint(message)
        return {"status": "warning", "message": message}

    # 更新 Inspection Event 的 supplier 字段
    inspection_event.supplier = supplier

    # 保存 Inspection Event
    inspection_event.save()
    frappe.db.commit()

    message = _("已成功添加 {0} 個項目。").format(added_count)
    if skipped_items:
        message += "\n" + _("跳過的項目：") + "\n" + "\n".join(skipped_items)
    frappe.msgprint(message)

    return {"status": "success", "message": message}