import frappe
from frappe import _
from frappe.model.document import Document
import json

from frappe.utils import format_date, format_time
from icalendar import Calendar, Event
from datetime import datetime
import io


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
    """回傳指定 Purchase Order 的所有明細"""
    if not po_name:
        frappe.throw("請提供有效的採購訂單編號")
    
    items = frappe.get_all(
        "Purchase Order Item",
        filters={"parent": po_name},
        fields=["name", "line",  "confirmed_qty", "article_number", "article_name"],
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

    # 檢查用戶對 Purchase Order 的讀取權限
    if not frappe.has_permission("Purchase Order", "read", po_name):
        frappe.log_error(
            message=f"User {frappe.session.user} lacks permission to read Purchase Order {po_name}",
            title="Permission Error in get_po_items_qcstatus"
        )
        frappe.throw(
            _("您沒有足夠的權限訪問此採購訂單，請聯繫管理員以獲取權限。"),
            frappe.PermissionError
        )

    # 查詢 Purchase Order Item
    items = frappe.get_all(
        "Purchase Order Item",
        filters={
            "parent": po_name,
            "qc_update_status": ["!=", "Passed"]
        },
        fields=["name", "line", "confirmed_qty", "article_number", "article_name"],
        order_by="line asc",
        ignore_permissions=True  # 僅限測試，生產環境應移除
    )

    # 記錄查詢結果
    frappe.log_error(
        message=f"Queried PO Items for {po_name}: {len(items)} items found",
        title="get_po_items_qcstatus"
    )

    return items

@frappe.whitelist()
def add_po_items_to_inspection_event(inspection_event_name, selected_items):
    """
    將選中的 Purchase Order Item 添加到 Inspection Event 的 po_items 表（Inspection Line），
    使用 po_number 和 po_item.line 檢查重複，跳過已存在項目並提示。
    
    Args:
        inspection_event_name (str): Inspection Event 的名稱
        selected_items (str or list): 選中的 Purchase Order Item 的 name 列表
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
        "Purchase Order Item",
        filters={"name": ["in", selected_items]},
        fields=["name", "line", "confirmed_qty", "article_number", "article_name", "parent"]
    )

    if not items:
        frappe.throw(_("無有效的項目被選擇。"))

    # 獲取當前 po_items 表中的 po_number 和 po_item.line 組合，用於檢查重複
    existing_items = set()
    for row in inspection_event.po_items:
        if row.po_number and row.po_item:
            po_item = frappe.get_doc("Purchase Order Item", {
                "parent": row.po_number,
                "line": row.po_item
            })
            if po_item.line is not None:
                existing_items.add((row.po_number, po_item.line))
    added_count = 0
    skipped_items = []
    # 假設第一個項目的 supplier 適用於所有項目（因為它們來自同一個 PO）
    supplier = None
    if items:
        po = frappe.get_doc("Purchase Order", items[0].parent)
        supplier = po.supplier if po.supplier else None

    # 將項目添加到 po_items 表，跳過已存在的項目
    for item in items:
        if (item.parent, item.line) not in existing_items:
            inspection_event.append("po_items", {
                "po_item": item.line,  # Link 到 Purchase Order Item
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


@frappe.whitelist()
def send_inspection_invitation(inspection_event_name):
    doc = frappe.get_doc("Inspection Event", inspection_event_name)
    
    if not doc.inspector:
        frappe.throw(_("請先設定 Inspector"))
    
    inspector_email = frappe.db.get_value("User", doc.inspector, "email")
    if not inspector_email:
        frappe.throw(_("Inspector 無 email"))
    
    # === 產生 .ics 附件 ===
    cal = Calendar()
    cal.add('prodid', '-//By Rydéns ERP//')
    cal.add('version', '2.0')
    
    event = Event()
    event.add('summary', f"Inspection Event: {doc.name}")
    event.add('dtstart', doc.starts_on)  # 直接使用 datetime 物件
    event.add('dtend', doc.ends_on or doc.starts_on)  # 直接使用 datetime 物件
    event.add('description', doc.description or "No description")
    event.add('location', doc.supplier or "N/A")
    event.add('uid', f"{doc.name}@byrydens.com")
    
    cal.add_component(event)
    
    ics_buffer = io.BytesIO()
    ics_buffer.write(cal.to_ical())
    ics_buffer.seek(0)
    
    # === 郵件內容 ===
    html = f"""
    <p>親愛的 {doc.inspector}，</p>
    <p>您有一個 Inspection Event 邀請：</p>
    <ul>
        <li><strong>事件</strong>: {doc.name}</li>
        <li><strong>開始</strong>: {format_date(doc.starts_on)} {format_time(doc.starts_on)}</li>
        <li><strong>結束</strong>: {format_date(doc.ends_on) if doc.ends_on else 'N/A'}</li>
        <li><strong>供應商</strong>: {doc.supplier or 'N/A'}</li>
        <li><strong>描述</strong>: {doc.description or 'N/A'}</li>
    </ul>
    <p>請匯入附件到 Outlook 日曆。</p>
    """
    
    # === 發送郵件 ===
    frappe.sendmail(
        recipients=[inspector_email],
        subject=f"Inspection Invitation: {doc.name} - {format_date(doc.starts_on)}",
        message=html,
        attachments=[{
            'fname': 'invitation.ics',
            'fcontent': ics_buffer.read(),
            'content_type': 'text/calendar'
        }]
    )
    
    return {"status": "success", "message": _("邀請已發送")}


@frappe.whitelist()
def update_qc_accepted_qty(purchase_order, line_number, aql_qty):
    try:
        po_item = frappe.get_doc("Purchase Order Item", {
            "parent": purchase_order,
            "line": line_number
        })
        po_item.qc_accepted_qty = (po_item.qc_accepted_qty or 0) + aql_qty
        po_item.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "qc_accepted_qty": po_item.qc_accepted_qty}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "update_qc_accepted_qty")
        return {"success": False, "error": str(e)}