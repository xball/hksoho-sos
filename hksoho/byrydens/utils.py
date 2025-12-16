import frappe
import base64
import mimetypes

from frappe import _

from frappe.utils.data import now_datetime, get_system_timezone, format_date, format_time  # 修正匯入為 get_system_timezone
from datetime import date
import pytz

def get_image_datauri(file_url):
    if not file_url:
        return ""
    
    # 取得檔案名稱（從 URL 擷取，如 /private/files/xxx.jpg -> xxx.jpg）
    file_name = file_url.split('/')[-1]
    
    # 取得 File 單據
    file_doc = frappe.get_value("File", {"file_url": file_url}, ["file_name", "is_private", "content"], as_dict=True)
    if not file_doc:
        return ""
    
    if file_doc.content:  # 若內容已儲存於資料庫（小檔案）
        content = file_doc.content
    else:  # 大檔案，從磁碟讀取
        if file_doc.is_private:
            file_path = frappe.get_site_path('private', 'files', file_name)
        else:
            file_path = frappe.get_site_path('public', 'files', file_name)
        
        with open(file_path, "rb") as f:
            content = f.read()
    
    # 轉為 Base64
    encoded = base64.b64encode(content).decode('utf-8')
    
    # 取得 MIME 類型（如 image/jpeg）
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = "image/jpeg"  # 預設 JPG
    
    return f"data:{mime_type};base64,{encoded}"




def send_daily_inspection_reminders():
    """
    每小時執行：根據 Inspector 時區發送早上 8 點提醒
    TEST MODE: Print sent emails to console
    """
    now_utc = now_datetime()  # 取得 UTC 時間
    print(f"\n=== Inspection Reminder Job Started at {frappe.utils.now()} (UTC) ===")

    # 找出所有 Open 事件（不限今天，以防時區差異）
    events = frappe.get_all(
        "Inspection Event",
        filters={
            "status": "Open",
            "send_reminder": 1,
            "inspector": [">", ""]
        },
        fields=["name", "inspector", "starts_on"]
    )

    if not events:
        print("No open events found. Job completed.\n")
        return

    sent_count = 0
    for event in events:
        try:
            doc = frappe.get_doc("Inspection Event", event.name)
            inspector_email = frappe.db.get_value("User", doc.inspector, "email")
            if not inspector_email:
                print(f"SKIP: Inspector '{doc.inspector}' has no email → Event: {doc.name}")
                continue

            # 取得 Inspector 的時區
            user_tz = frappe.db.get_value("User", doc.inspector, "time_zone") or get_system_timezone()  # 修正為 get_system_timezone
            tz = pytz.timezone(user_tz)
            now_local = now_utc.astimezone(tz)  # 轉換為當地時間
            today_local = now_local.date()  # 當地今日日期

            # 檢查事件 starts_on 是否為當地今天（基於時區調整）
            starts_on_local = frappe.utils.get_datetime(doc.starts_on).astimezone(tz).date()
            if starts_on_local != today_local:
                print(f"SKIP: Event {doc.name} not today in {user_tz} (starts_on: {starts_on_local})")
                continue

            # 檢查最後發送記錄
            log_name = frappe.db.get_value("Reminder Log", {"user": doc.inspector})
            last_sent = None
            if log_name:
                last_sent = frappe.db.get_value("Reminder Log", log_name, "last_sent_date")
            else:
                # 如果無記錄，建立新的一筆
                new_log = frappe.get_doc({
                    "doctype": "Reminder Log",
                    "user": doc.inspector,
                    "last_sent_date": None
                }).insert(ignore_permissions=True)
                log_name = new_log.name

            # 如果是當地早上 8 點，且今天尚未發送
            if now_local.hour == 8 and (not last_sent or last_sent < today_local):
                # === 測試用：印出即將寄送的資訊 ===
                print(f"SENDING REMINDER →")
                print(f"   Event     : {doc.name}")
                print(f"   Inspector : {doc.inspector}")
                print(f"   Email     : {inspector_email}")
                print(f"   Starts On : {doc.starts_on} (Local: {now_local})")
                print("-" * 50)

                # 實際寄信
                subject = f"Inspection Event Reminder: {doc.name} - {format_date(doc.starts_on)}"
                html_body = get_email_html(doc)

                frappe.sendmail(
                    recipients=[inspector_email],
                    subject=subject,
                    content=html_body,
                    delayed=False
                )

                sent_count += 1
                print(f"SUCCESS: Email sent to {inspector_email}\n")

                # 更新最後發送日期
                frappe.db.set_value("Reminder Log", log_name, "last_sent_date", today_local)

        except Exception as e:
            error_msg = str(e)
            print(f"FAILED: {doc.name} → {error_msg}\n")
            frappe.log_error(f"Inspection reminder failed for {doc.name}: {error_msg}")

    print(f"=== Job Completed: {sent_count} reminder(s) sent ===\n")


def get_email_html(doc):
    """Generate HTML email for Inspection Event (Confirmed QTY 已移除)"""
    po_items = doc.get("po_items") or []
    
    # === 安全欄位映射（防呆，支援不同專案的欄位名稱）===
    child_meta = frappe.get_meta("Inspection Line")
    field_map = {
        "line": next((f for f in child_meta.fields if f.fieldname in ["line", "idx", "po_line"]), None),
        "article_number": next((f for f in child_meta.fields if f.fieldname in ["article_number", "item_code", "article_no"]), None),
        "article_name": next((f for f in child_meta.fields if f.fieldname in ["article_name", "item_name"]), None),
        "confirmed_qty": next((f for f in child_meta.fields if f.fieldname in ["confirmed_qty", "qty", "po_qty"]), None),
        # confirmed_qty 已徹底移除
    }

    rows = ""
    for item in po_items:
        line = getattr(item, field_map["line"].fieldname, "") if field_map["line"] else ""
        article_number = getattr(item, field_map["article_number"].fieldname, "") if field_map["article_number"] else ""
        article_name = getattr(item, field_map["article_name"].fieldname, "") if field_map["article_name"] else ""
        req_qty = getattr(item, field_map["confirmed_qty"].fieldname, 0) if field_map["confirmed_qty"] else 0

        rows += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 8px;">{line}</td>
            <td style="padding: 8px;">{article_number}</td>
            <td style="padding: 8px;">{article_name}</td>
            <td style="padding: 8px; text-align: right;">{req_qty}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="4" style="text-align:center; color:#999; padding:20px;">No PO Items</td></tr>'

    supplier_name = frappe.db.get_value("Partner", doc.supplier, "partner_name") if doc.supplier else "N/A"

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="background: #1a5fb4; color: white; padding: 16px; text-align: center;">
            <h2 style="margin:0;">Inspection Event Reminder</h2>
        </div>
        <div style="padding: 20px; background: #f9f9f9;">
            <h3 style="color: #1a5fb4; margin-top:0; border-bottom: 2px solid #1a5fb4; padding-bottom: 8px;">{doc.name}</h3>
            
            <table style="width:100%; margin:16px 0; font-size:14px;">
                <tr><td style="font-weight:bold; width:140px;">Inspector:</td><td>{doc.inspector or 'N/A'}</td></tr>
                <tr><td style="font-weight:bold;">Supplier:</td><td>{supplier_name}</td></tr>
                <tr><td style="font-weight:bold;">Type:</td><td>{doc.type or ''}</td></tr>
                <tr><td style="font-weight:bold;">Inspection:</td><td>{doc.inspection or ''}</td></tr>
                <tr><td style="font-weight:bold;">Starts On:</td><td>{format_date(doc.starts_on)} {format_time(doc.starts_on)}</td></tr>
                <tr><td style="font-weight:bold;">Ends On:</td><td>{doc.ends_on and (format_date(doc.ends_on) + ' ' + format_time(doc.ends_on)) or 'N/A'}</td></tr>
                <tr><td style="font-weight:bold;">Status:</td><td><span style="background:#28a745; color:white; padding:2px 8px; border-radius:4px; font-size:12px;">{doc.status or ''}</span></td></tr>
            </table>

            <h4 style="color:#1a5fb4; margin:24px 0 12px;">PO Items</h4>
            <table style="width:100%; border-collapse: collapse; font-size:13px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <thead style="background:#e9ecef;">
                    <tr>
                        <th style="padding:8px; text-align:left; border-bottom:2px solid #1a5fb4;">Line</th>
                        <th style="padding:8px; text-align:left; border-bottom:2px solid #1a5fb4;">Article #</th>
                        <th style="padding:8px; text-align:left; border-bottom:2px solid #1a5fb4;">Article Name</th>
                        <th style="padding:8px; text-align:right; border-bottom:2px solid #1a5fb4;">Ordered QTY</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>

            {f'<h4 style="color:#1a5fb4; margin:24px 0 12px;">Description</h4><div style="background:#fff; padding:12px; border-left:4px solid #1a5fb4; border-radius:4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-size:13px;">{doc.description}</div>' if doc.description else ''}

            <hr style="margin:24px 0; border:none; border-top:1px dashed #ccc;">
            <p style="font-size:12px; color:#666; text-align:center;">
                Please log in to ERP to update inspection results.
            </p>
        </div>
    </div>
    """

@frappe.whitelist()
def load_product_images_to_po_items(po_name):
    """
    One-click sync from Product → Purchase Order Item
    Automatically fills:
    • Primary Image
    • Inner box CBM
    • Inner box weight
    • Pieces per carton
    • Customs tariff code (HS Origin)
    Only updates fields that are blank or different.
    """
    if not po_name:
        frappe.throw("PO name is required")

    # Query child table directly to avoid cache issues
    items = frappe.get_all(
        "Purchase Order Item",
        filters={"parent": po_name},
        fields=[
            "name", "article_number", "line",
            "article_photo", "carton_cbm", "unit_net_kg",
            "pcs_per_cartion", "hs_origin"
        ]
    )

    if not items:
        return {"updated": 0, "skipped": 0, "total": 0, "details": []}

    updated_count = 0
    detail_log = []

    for item in items:
        if not item.article_number:
            continue

        # Fetch multiple fields from Product in one query
        product_data = frappe.db.get_value(
            "Product",
            item.article_number,
            [
                "primary_image",
                "gross_cbm_innerunit_box",
                "gross_weight_kg_innerunit_box",
                "units_in_carton_pieces_per_carton",
                "customs_tariff_code"
            ],
            as_dict=True
        )

        if not product_data:
            continue

        changes = []

        # 1. Primary Image
        if product_data.primary_image and product_data.primary_image != item.article_photo:
            frappe.db.set_value("Purchase Order Item", item.name, "article_photo", product_data.primary_image)
            changes.append("Primary Image")

        # 2. Inner box CBM
        if product_data.gross_cbm_innerunit_box is not None:
            current = item.carton_cbm or 0
            if abs(float(current) - float(product_data.gross_cbm_innerunit_box)) > 0.0001:
                frappe.db.set_value("Purchase Order Item", item.name, "carton_cbm", product_data.gross_cbm_innerunit_box)
                changes.append("Inner Box CBM")

        # 3. Inner box weight
        if product_data.gross_weight_kg_innerunit_box is not None:
            current = item.unit_net_kg or 0
            if abs(float(current) - float(product_data.gross_weight_kg_innerunit_box)) > 0.0001:
                frappe.db.set_value("Purchase Order Item", item.name, "unit_net_kg", product_data.gross_weight_kg_innerunit_box)
                changes.append("Inner Box Weight")

        # 4. Pieces per carton
        if product_data.units_in_carton_pieces_per_carton:
            if item.pcs_per_cartion != product_data.units_in_carton_pieces_per_carton:
                frappe.db.set_value("Purchase Order Item", item.name, "pcs_per_cartion", product_data.units_in_carton_pieces_per_carton)
                changes.append("Pcs per Carton")

        # 5. Customs tariff code (HS Origin)
        if product_data.customs_tariff_code and product_data.customs_tariff_code != item.hs_origin:
            frappe.db.set_value("Purchase Order Item", item.name, "hs_origin", product_data.customs_tariff_code)
            changes.append("HS Code")

        if changes:
            updated_count += 1
            line_no = item.line or "?"
            detail_log.append(f"Line {line_no}: {', '.join(changes)}")

    # Clear cache so users see changes immediately
    if updated_count > 0:
        frappe.clear_document_cache("Purchase Order", po_name)
        frappe.db.set_value("Purchase Order", po_name, "modified", frappe.utils.now(), update_modified=False)
        frappe.db.commit()

    return {
        "updated": updated_count,
        "skipped": len(items) - updated_count,
        "total": len(items),
        "details": detail_log
    }
import frappe
import os

@frappe.whitelist()
def make_product_images_public():
    """
    終極容錯版：把所有 Product 用的 Private 圖強制轉 Public
    即使實體檔案不見了也強制成功！
    """
    count_fixed = 0
    count_skipped = 0
    count_error = 0

    products = frappe.get_all(
        "Product",
        filters={"primary_image": ["like", "%/private/files/%"]},
        fields=["name", "article_number", "primary_image"]
    )

    print(f"發現 {len(products)} 筆 Product 使用 Private 圖片，正在強制轉換...")

    for p in products:
        old_url = p.primary_image
        filename = old_url.split("/")[-1]
        
        try:
            # 嘗試用 file_url 找 File
            file_doc = frappe.get_doc("File", {"file_url": old_url})
        except:
            # 找不到就用檔名搜（常見問題）
            files = frappe.get_all("File", filters={"file_name": filename}, fields=["name"])
            if not files:
                print(f"完全找不到檔案（已跳過）: {p.article_number} → {old_url}")
                count_error += 1
                continue
            file_doc = frappe.get_doc("File", files[0].name)

        # 強制關閉 Frappe 的檔案存在性檢查
        file_doc.flags.ignore_missing_file = True
        
        if not file_doc.is_private:
            count_skipped += 1
            continue

        try:
            # 關鍵！直接用 db_set 繞過所有驗證
            frappe.db.set_value("File", file_doc.name, {
                "is_private": 0,
                "folder": "Home/Attachments"
            }, update_modified=False)

            # 直接修正 Product 的 URL（從 private → public）
            new_url = old_url.replace("/private/files/", "/files/")
            frappe.db.set_value("Product", p.name, "primary_image", new_url)

            print(f"強制轉 Public 成功: {p.article_number} → {new_url}")
            count_fixed += 1

        except Exception as e:
            print(f"轉換失敗（已跳過）: {p.article_number} → {str(e)}")
            count_error += 1

    frappe.db.commit()
    
    print("\n" + "="*80)
    print("【大功告成】所有 Product 主圖已強制轉為 Public！")
    print(f"成功轉換：{count_fixed} 張")
    print(f"已為 Public：{count_skipped} 張")
    print(f"跳過/錯誤：{count_error} 張（不影響其他圖片）")
    print("="*80)
    print("所有使用者現在都可以看到產品主圖了！")
    
    return {"fixed": count_fixed, "skipped": count_skipped, "error": count_error}

import frappe
from frappe.utils import get_last_day
from frappe import _

@frappe.whitelist()
def get_due_po_details(year, month_name):
    month_map = {
        "January": "01", "February": "02", "March": "03", "April": "04",
        "May": "05", "June": "06", "July": "07", "August": "08",
        "September": "09", "October": "10", "November": "11", "December": "12"
    }
    
    month = month_map.get(month_name)
    if not month:
        return {"title": "錯誤", "data": [], "columns": [], "message": "月份格式錯誤"}

    start = f"{year}-{month}-01"
    end = get_last_day(start)

    data = frappe.db.sql("""
        SELECT 
            po.name AS po_number,
            po.supplier AS partner_id,
            COALESCE(p.partner_name, po.supplier, 'Unknown') AS partner_name,
            po.po_shipdate,
            po.po_status,
            po.order_purchase_currency AS currency,
            SUM((item.confirmed_qty - COALESCE(item.booked_qty, 0)) * item.unit_price) AS undelivered_value
        FROM `tabPurchase Order` po
        LEFT JOIN `tabPartner` p ON p.partner_id = po.supplier
        JOIN `tabPurchase Order Item` item ON item.parent = po.name
        WHERE po.po_shipdate BETWEEN %s AND %s
          AND item.confirmed_qty > COALESCE(item.booked_qty, 0)
          AND item.unit_price > 0
        GROUP BY po.name
        HAVING undelivered_value > 0
        ORDER BY po.po_shipdate DESC, po.name DESC
    """, (start, end), as_dict=1)

    columns = [
        {"label": "PO Number", "fieldname": "po_number", "fieldtype": "Link", "options": "Purchase Order", "width": 140},
        {"label": "Partner ID", "fieldname": "partner_id", "fieldtype": "Data", "width": 120},
        {"label": "Partner Name", "fieldname": "partner_name", "fieldtype": "Data", "width": 280},
        {"label": "Ship Date", "fieldname": "po_shipdate", "fieldtype": "Date", "width": 110},
        {"label": "Status", "fieldname": "po_status", "fieldtype": "Data", "width": 100},
        {"label": "Currency", "fieldname": "currency", "fieldtype": "Data", "width": 80},
        {"label": "Undelivered Value", "fieldname": "undelivered_value", "fieldtype": "Currency", "width": 160},
    ]

    return {
        "title": f"{month_name} {year} – Orders Due to Pay ({len(data)} POs)",
        "columns": columns,
        "data": data
    }