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
    """Generate HTML email with safe CSS (no #RRGGBBAA)"""
    po_items = doc.get("po_items") or []
    
    # === 安全欄位映射（防呆）===
    child_meta = frappe.get_meta("Inspection Line")
    field_map = {
        "line": next((f for f in child_meta.fields if f.fieldname in ["line", "idx", "po_line"]), None),
        "article_number": next((f for f in child_meta.fields if f.fieldname in ["article_number", "item_code", "article_no"]), None),
        "article_name": next((f for f in child_meta.fields if f.fieldname in ["article_name", "item_name"]), None),
        "requested_qty": next((f for f in child_meta.fields if f.fieldname in ["requested_qty", "qty"]), None),
        "confirmed_qty": next((f for f in child_meta.fields if f.fieldname in ["confirmed_qty", "received_qty"]), None),
    }

    rows = ""
    for item in po_items:
        line = getattr(item, field_map["line"].fieldname, "") if field_map["line"] else ""
        article_number = getattr(item, field_map["article_number"].fieldname, "") if field_map["article_number"] else ""
        article_name = getattr(item, field_map["article_name"].fieldname, "") if field_map["article_name"] else ""
        req_qty = getattr(item, field_map["requested_qty"].fieldname, 0) if field_map["requested_qty"] else 0
        conf_qty = getattr(item, field_map["confirmed_qty"].fieldname, 0) if field_map["confirmed_qty"] else 0

        rows += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 8px;">{line}</td>
            <td style="padding: 8px;">{article_number}</td>
            <td style="padding: 8px;">{article_name}</td>
            <td style="padding: 8px; text-align: right;">{req_qty}</td>
            <td style="padding: 8px; text-align: right;">{conf_qty}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="5" style="text-align:center; color:#999; padding:20px;">No PO Items</td></tr>'

    supplier_name = frappe.db.get_value("Partner", doc.supplier, "partner_name") if doc.supplier else "N/A"

    # === 關鍵：所有陰影改用 rgba() ===
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="background: #1a5fb4; color: white; padding: 16px; text-align: center;">
            <h2 style="margin:0;">Inspection Event Reminder</h2>
        </div>
        <div style="padding: 20px; background: #f9f9f9;">
            <h3 style="color: #1a5fb4; margin-top:0; border-bottom: 2px solid #1a5fb4; padding-bottom: 8px;">{doc.name}</h3>
            
            <table style="width:100%; margin:16px 0; font-size:14px;">
                <tr><td style="font-weight:bold; width:140px;">Inspector:</td><td>{doc.inspector}</td></tr>
                <tr><td style="font-weight:bold;">Supplier:</td><td>{supplier_name}</td></tr>
                <tr><td style="font-weight:bold;">Type:</td><td>{doc.type}</td></tr>
                <tr><td style="font-weight:bold;">Inspection:</td><td>{doc.inspection}</td></tr>
                <tr><td style="font-weight:bold;">Starts On:</td><td>{format_date(doc.starts_on)} {format_time(doc.starts_on)}</td></tr>
                <tr><td style="font-weight:bold;">Ends On:</td><td>{doc.ends_on and (format_date(doc.ends_on) + ' ' + format_time(doc.ends_on)) or 'N/A'}</td></tr>
                <tr><td style="font-weight:bold;">Status:</td><td><span style="background:#28a745; color:white; padding:2px 8px; border-radius:4px; font-size:12px;">{doc.status}</span></td></tr>
            </table>

            <h4 style="color:#1a5fb4; margin:24px 0 12px;">PO Items</h4>
            <table style="width:100%; border-collapse: collapse; font-size:13px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <thead style="background:#e9ecef;">
                    <tr>
                        <th style="padding:8px; text-align:left; border-bottom:2px solid #1a5fb4;">Line</th>
                        <th style="padding:8px; text-align:left; border-bottom:2px solid #1a5fb4;">Article #</th>
                        <th style="padding:8px; text-align:left; border-bottom:2px solid #1a5fb4;">Article Name</th>
                        <th style="padding:8px; text-align:right; border-bottom:2px solid #1a5fb4;">Req QTY</th>
                        <th style="padding:8px; text-align:right; border-bottom:2px solid #1a5fb4;">Conf QTY</th>
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
    
# Server Script → Script Type = API
# API Method 欄位請填： get_due_po_details

@frappe.whitelist()
def get_due_po_details(year, month_name):
    
    print(f"\n{'='*60}")
    print(f"DEBUG: Starting get_due_po_details")
    print(f"DEBUG: year = {year}, month_name = {month_name}")
    print(f"{'='*60}\n")
    month_map = {"January":"01","February":"02","March":"03","April":"04","May":"06",
                 "July":"07","August":"08","September":"09","October":"10","November":"11","December":"12"}
    month = month_map.get(month_name)
    if not month: frappe.throw("Invalid month")

    start = f"{year}-{month}-01"
    end = frappe.utils.get_last_day(start)

    print("DEBUG: Executing SQL query...")

    data = frappe.db.sql("""
        SELECT 
            po.name AS po_number,
            po.supplier AS partner_id,
            COALESCE(p.partner_name, po.supplier) AS partner_name,
            po.po_shipdate,
            po.po_status,
            po.order_purchase_currency AS currency,
            SUM(item.confirmed_qty * item.unit_price) AS undelivered_value
        FROM `tabPurchase Order` po
        LEFT JOIN `tabPartner` p ON p.partner_id = po.supplier
        JOIN `tabPurchase Order Item` item ON item.parent = po.name
        WHERE po.po_shipdate BETWEEN %s AND %s AND COALESCE(item.order_status, '') != "Shipped"
        GROUP BY po.name
        ORDER BY po.po_shipdate DESC
    """, (start, end), as_dict=1)
    
    print(f"DEBUG: Query returned {len(data)} records\n")
    
    if data:
        print("DEBUG: First record:")
        print(f"  {data[0]}\n")
        
    columns = [
        {"label": "PO Number", "fieldname": "po_number", "fieldtype": "Link", "options": "Purchase Order", "width": 130},
        {"label": "Partner ID", "fieldname": "partner_id", "fieldtype": "Data", "width": 110},
        {"label": "Partner Name", "fieldname": "partner_name", "fieldtype": "Data", "width": 220},
        {"label": "Ship Date", "fieldname": "po_shipdate", "fieldtype": "Date", "width": 110},
        {"label": "Status", "fieldname": "po_status", "fieldtype": "Data", "width": 90},
        {"label": "Undelivered Value", "fieldname": "undelivered_value", "fieldtype": "Currency", "width": 140},
        {"label": "Currency", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80}
    ]
    result = {
        "title": f"{month_name} {year} – Orders Due to Pay ({len(data)} POs)",
        "subtitle": "",
        "columns": columns,
        "data": data,
        "print_settings": {}
    }
    print("DEBUG: Building return object...")
    print(f"  title: {result['title']}")
    print(f"  subtitle: '{result['subtitle']}'")
    print(f"  columns: {len(result['columns'])} columns")
    print(f"  data: {len(result['data'])} rows")
    print(f"  print_settings: {result['print_settings']}")
    print(f"\n{'='*60}")
    print("DEBUG: Function completed successfully")
    print(f"{'='*60}\n")
    
    print("\n" + "="*80)
    print(f"ALL {len(result['data'])} PO RECORDS - COMPLETE DATA")
    print("="*80)

    for i, row in enumerate(result['data'], 1):
        print(f"\n{'─'*80}")
        print(f"Record {i} of {len(result['data'])}")
        print(f"{'─'*80}")
        print(f"  PO Number         : {row['po_number']}")
        print(f"  Partner ID        : {row['partner_id']}")
        print(f"  Partner Name      : {row['partner_name']}")
        print(f"  Ship Date         : {row['po_shipdate']}")
        print(f"  Status            : {row['po_status']}")
        print(f"  Currency          : {row['currency']}")
        print(f"  Undelivered Value : {row['undelivered_value']:,.2f}")

    print("\n" + "="*80)
    print(f"TOTAL RECORDS: {len(result['data'])}")
    print("="*80)    
    
    
    return result


@frappe.whitelist()
def load_product_images_to_po_items(po_name):
    """
    將 Product 的 primary_image 自動帶入 Purchase Order 的每個 PO Item 的 article_photo 欄位
    只會填「空白」的，避免覆蓋使用者手動上傳的圖
    """
    if not po_name:
        frappe.throw("請提供 PO 名稱")

    po = frappe.get_doc("Purchase Order", po_name)
    updated = 0
    skipped = 0

    for item in po.po_items:
        if not item.article_number:
            continue

        # 從 Product 取主圖
        primary_image = frappe.db.get_value(
            "Product",
            item.article_number,
            "primary_image"
        )

        if not primary_image:
            continue  # Product 沒有圖，跳過

    # 強制覆蓋全部（不管原本有沒有圖）
        if primary_image != item.article_photo:
            frappe.db.set_value(
                "Purchase Order Item",
                item.name,
                "article_photo",
                primary_image
            )
            updated += 1
        else:
            skipped += 1

    # 可選：更新 PO 修改時間
    frappe.db.set_value("Purchase Order", po_name, "modified", frappe.utils.now())

    return {
        "updated": updated,
        "skipped": skipped,
        "total": len(po.po_items)
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