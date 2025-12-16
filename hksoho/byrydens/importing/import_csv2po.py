import csv
import os
import glob
import shutil
import frappe
from datetime import datetime
from frappe.desk.form.utils import add_comment
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta 

# DocType 定義
PO_DOCTYPE = "Purchase Order"
PO_ITEM_DOCTYPE = "Purchase Order Item"

# 從 site_config 獲取路徑，預設值作為備用
INPUT_DIR = frappe.get_site_config().get("po_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("po_import_proceed_dir", "/home/ftpuser/done")
LOG_FILE = frappe.get_site_config().get("po_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/po_import.log")

# 設置日誌
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR, filename=LOG_FILE, filemode='a', format='[%(asctime)s] %(levelname)s: %(message)s')

# 儲存 PO 和 PO 項目的資料結構
purchase_orders = {}

# 用於收集日誌訊息
log_buffer = StringIO()

# 格式化日期
def format_date(date_str):
    if not date_str:
        return None
    try:
        # 先嘗試解析 YYYY-MM-DD 格式
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        try:
            # 再嘗試解析 DD/MM/YYYY 格式
            return datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            logger.warning(f"無效的日期格式: {date_str}")
            return None
        
# 檢查 Link 欄位是否存在
def validate_link_field(doctype, fieldname, value):
    if not value:
        return None
    value = value.strip()  # 去除首尾空白
    exists = frappe.db.exists(doctype, {fieldname: value})
    if exists:
        return exists
    else:
        msg = f"{doctype} 中未找到 {fieldname}: {value}"
        logger.warning(msg)
        print(msg)
        return None

# 檢查 po_number 是否存在
def check_po_exists(po_number):
    return frappe.db.exists(PO_DOCTYPE, {"po_number": po_number})

# 查詢 PO 項目
def get_poitem(po_number):
    try:
        poitems = frappe.get_all(PO_ITEM_DOCTYPE, filters={"purchase_order": po_number}, fields=["*"])
        return poitems
    except Exception as e:
        msg = f"查詢採購訂單項目 {po_number} 失敗: {e}"
        logger.error(msg)
        print(msg)
        return []

# 讀取 CSV 檔案
def import_po_data(file_path):
    try:
        with open(file_path, mode='r', encoding='cp1252') as file:
            reader = csv.reader(file, delimiter='\t')
            current_po = None
            for row in reader:
                if not row:
                    continue
                row_type = row[0]
                # 處理 PO (01)
                if row_type == "01":
                    address_parts = [row[13], row[14], row[15]]  # 地址、郵政編碼、城市
                    address = ", ".join(part for part in address_parts if part)
                    po_data = {
                        "po_number": row[1],
                        "supplier_code": row[2],
                        "po_placed": row[3] if row[3] else None,
                        "payment_terms": row[6],
                        "delivery_terms": row[7],
                        "delivery_mode": row[8],
                        "requested_forwarder": row[12],
                        "delivery_address": address,
                        "purchaser": row[18],
                        "need_sample": row[19],
                        "responsible": row[20],
                        "purpose": row[21],
                        "directdelivery": row[22],
                        "items": []
                    }
                    current_po = po_data
                    purchase_orders[row[1]] = current_po
                # 處理 PO 項目 (02)
                elif row_type == "02" and current_po:
                    item_data = {
                        "line": row[2],
                        "article_number": row[3],
                        "confirmed_qty": int(row[4]) if row[4] else 0,
                        "article_name": row[6],
                        "supplier_art_number": row[7],
                        "unit_price": float(row[8]) if row[8] else 0,
                        "price_currency": row[9],
                        "requested_finish_date": row[12] if row[12] else None,
                        "requested_eta": row[13] if row[13] else None,
                        "short_description": []
                    }
                    current_po["items"].append(item_data)
                # 處理短描述 (03)
                elif row_type == "03" and current_po and current_po["items"]:
                    current_po["items"][-1]["short_description"].append(row[3])
    except FileNotFoundError:
        msg = f"檔案未找到: {file_path}"
        logger.error(msg)
        print(msg)
    except Exception as e:
        msg = f"處理檔案時發生錯誤: {e}"
        logger.error(msg)
        print(msg)

# 創建或更新採購訂單
def create_purchase_order(po_data):
    po_exists = check_po_exists(po_data["po_number"])
    
    # 驗證 Link 欄位
    supplier_code = validate_link_field("Partner", "name", po_data["supplier_code"])
    purchaser = validate_link_field("User", "bio", po_data["purchaser"])
    responsible = validate_link_field("User", "bio", po_data["responsible"])
    order_type = "Standard" if po_data["need_sample"] == "N" else "Sample"
    delivery_terms = validate_link_field("Delivery Term", "name", po_data["delivery_terms"])
    payment_terms = validate_link_field("Payment Term", "code", po_data["payment_terms"])
    delivery_mode = "BY BOAT" if po_data["delivery_mode"] == "1" else "BY AIR"
    
    if not supplier_code:
        msg = f"無效的 supplier_code: {po_data['supplier_code']}，無法創建或更新採購訂單"
        logger.error(msg)
        print(msg)
        return False, msg
    partner = validate_link_field("Partner", "name", supplier_code)
    qc_required = 1 if partner and frappe.get_value("Partner", partner, "quality_control") == "Always Requested" else 0

###############################################

    # 先從 supplier Partner 取 origin_country / origin_port
    origin_country = None
    origin_port_location = None
    destination_port_location = None

    # 1) Supplier → origin_country & origin_port.location
    if supplier_code:
        # 這裡 supplier_code 已經是 Partner.name（前面 validate_link_field 回傳的 exists 值）
        partner_doc = frappe.get_doc("Partner", supplier_code)
        origin_country = partner_doc.origin_country

        if partner_doc.origin_port:
            # 取 Load-Dest Port.location
            origin_port_location = frappe.db.get_value(
                "Load-Dest Port",
                partner_doc.origin_port,
                "location"
            )

    # 2) Buyer → destination_port.location
    # po_data["buyer_code"] 你目前沒帶，如果有 Buyer 代碼，這裡要先從 CSV 塞進 po_data 才用得到
    buyer_code = po_data.get("buyer_code")
    if buyer_code:
        buyer_partner = validate_link_field("Partner", "name", buyer_code)
        if buyer_partner:
            buyer_doc = frappe.get_doc("Partner", buyer_partner)
            if buyer_doc.destination_port:
                destination_port_location = frappe.db.get_value(
                    "Load-Dest Port",
                    buyer_doc.destination_port,
                    "location"
                )

    # === 先處理每一個 PO item 的日期 ===
    for item in po_data["items"]:
        if item.get("requested_finish_date"):
            try:
                finish_str = format_date(item["requested_finish_date"])
                if finish_str:
                    finish_date = datetime.strptime(finish_str, "%Y-%m-%d").date()
                    req_shipdate = finish_date + timedelta(days=14)
                    item["requested_shipdate"] = req_shipdate.strftime("%Y-%m-%d")

                    req_eta_date = req_shipdate + timedelta(days=60)
                    item["requested_eta"] = req_eta_date.strftime("%Y-%m-%d")
            except Exception as e:
                msg = f"計算項目日期失敗 (line {item.get('line')}): {e}"
                logger.warning(msg)
                print(msg)

    # === po_shipdate 仍然用「第一個有 requested_eta 的項目 - 60 天」 ===
    po_shipdate = None
    for item in po_data["items"]:
        if item.get("requested_eta"):
            try:
                eta_str = format_date(item["requested_eta"])
                if eta_str:
                    eta_date = datetime.strptime(eta_str, "%Y-%m-%d").date()
                    po_shipdate_date = eta_date - timedelta(days=60)
                    po_shipdate = po_shipdate_date.strftime("%Y-%m-%d")
                    break
            except Exception as e:
                msg = f"計算 po_shipdate 時發生錯誤 (requested_eta={item.get('requested_eta')}): {e}"
                logger.warning(msg)
                print(msg)

    # === Requested DC ETA = PO ShipDate + 60 天（與前端 refresh 規則一致） ===
    requested_dc_eta = None
    if po_shipdate:
        try:
            ship_date = datetime.strptime(po_shipdate, "%Y-%m-%d").date()
            dc_eta_date = ship_date + timedelta(days=60)
            requested_dc_eta = dc_eta_date.strftime("%Y-%m-%d")
        except Exception as e:
            msg = f"計算 requested_dc_eta 時發生錯誤 (po_shipdate={po_shipdate}): {e}"
            logger.warning(msg)
            print(msg)

###############################################



    updated_fields = []
    action = "Created"

    # 載入或創建 PO
    if po_exists:
        po = frappe.get_doc(PO_DOCTYPE, {"po_number": po_data["po_number"]})
        # 檢查工作流程狀態
        workflow_state = frappe.get_value(PO_DOCTYPE, po.name, "workflow_state")
        # if workflow_state not in ["Draft", "Submitted", "Supplier Confirmed"]:
        if workflow_state not in ["Draft", "Submitted"]:
            msg = f"採購訂單 {po_data['po_number']} 狀態為 {workflow_state}，無法更新"
            logger.warning(msg)
            print(msg)
            return False, msg
        msg = f"採購訂單 {po_data['po_number']} 已存在，正在更新..."
        logger.info(msg)
        print(msg)
        action = "Updated"
    else:
        po = frappe.new_doc(PO_DOCTYPE)
        msg = f"創建新採購訂單: {po_data['po_number']}"
        logger.info(msg)
        print(msg)

    # 更新主表欄位（僅更新有變更的欄位）
    po_fields = {
        "po_number": po_data["po_number"],
        "supplier": supplier_code,
        "purchaser": purchaser,
        "po_placed": format_date(po_data["po_placed"]),
        "payment_terms": payment_terms,
        "delivery_mode": delivery_mode,
        "delivery_terms": delivery_terms,
        "delivery_address": po_data["delivery_address"],
        "requested_forwarder": po_data["requested_forwarder"],
        "responsible": responsible,
        "order_type": order_type,
        "purpose": po_data["purpose"],
        "qc_requested": qc_required,
        "po_shipdate": po_shipdate,
        "origin_country": origin_country,                 
        "origin_port": origin_port_location,              
        "destination_port": destination_port_location ,         
        "requested_dc_eta": requested_dc_eta
    }

    if po_exists:
        for field, new_value in po_fields.items():
            old_value = getattr(po, field, None)
            if old_value != new_value:
                setattr(po, field, new_value)
                updated_fields.append(f"{field}: {old_value} -> {new_value}")
    else:
        for field, value in po_fields.items():
            setattr(po, field, value)
    logger.info(f"Going 處理子表")
    # 處理子表
    existing_items = {item.line: item for item in po.po_items if item.line} if po_exists else {}
    new_items = []
    for item in po_data["items"]:
        article_number = validate_link_field("Product", "name", item["article_number"])
        logger.info(f"detect article_number: {item['article_number']}")
        if not article_number:
            msg = f"無效的 article_number: {item['article_number']}，跳過項目"
            logger.warning(msg)
            print(msg)
            continue

        item_data = {
            "article_number": article_number,
            "confirmed_qty": item["confirmed_qty"],
            "unit_price": item["unit_price"],
            "price_currency": item["price_currency"],
            "article_name": item["article_name"],
            "short_description": "\n".join(item["short_description"]),
            "requested_finish_date": format_date(item["requested_finish_date"]),
            "requested_shipdate": format_date(item["requested_shipdate"]),        
            "requested_eta": format_date(item["requested_eta"]),
            "line": item["line"],
            "supplier_art_number": item["supplier_art_number"],
            "po_number": po_data["po_number"]
        }

        if po_exists and item["line"] in existing_items:
            existing_item = existing_items[item["line"]]
            for field, new_value in item_data.items():
                old_value = getattr(existing_item, field, None)
                if old_value != new_value:
                    setattr(existing_item, field, new_value)
                    updated_fields.append(f"Item {item['line']} {field}: {old_value} -> {new_value}")
            new_items.append(existing_item.as_dict())
        else:
            new_items.append(item_data)

    po.set("po_items", new_items)
    logger.info(f"after po.set")

    try:
        po.save(ignore_permissions=True)
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Import CSV file - {action}"
        if updated_fields:
            comment += f"\nUpdated fields:\n" + "\n".join(updated_fields)
        add_activity_message(PO_DOCTYPE, po.name, comment, 'Info')
        frappe.db.commit()
        
    # === 新增：匯入完立刻自動補產品圖！===
        try:
            from hksoho.byrydens.utils import load_product_images_to_po_items
            result = load_product_images_to_po_items(po.name)
            updated_images = result.get("updated", 0)
            if updated_images > 0:
                add_activity_message(PO_DOCTYPE, po.name, 
                    f"Auto-loaded {updated_images} product image", 
                    'Info')
                print(f"PO {po.name} → auto-loaded {updated_images} product image！")
            else:
                print(f"PO {po.name} → no new product images to load.")
        except Exception as e:
            error_msg = f"Cannot load product image : {str(e)}"
            logger.warning(error_msg)
            print(error_msg)
            add_activity_message(PO_DOCTYPE, po.name, error_msg, 'Warning')        
    ##################################################    
        
        msg = f"已{action}採購訂單: {po.name}"
        logger.info(msg)
        print(msg)
        return True, msg
    except Exception as e:
        msg = f"{action}採購訂單 {po_data['po_number']} 失敗: {e}"
        logger.error(msg)
        print(msg)
        return False, msg

# 添加活動記錄
def add_activity_message(doctype_name, doc_name, message, comment_type='Info'):
    try:
        doc = frappe.get_doc(doctype_name, doc_name)
        doc.add_comment(comment_type, message)
        frappe.db.commit()
        msg = f"已添加活動記錄到 {doctype_name} {doc_name}: {message}"
        logger.info(msg)
        print(msg)
        return True, msg
    except Exception as e:
        msg = f"添加活動記錄到 {doctype_name} {doc_name} 失敗: {e}"
        logger.error(msg)
        print(msg)
        return False, msg

# 發送電子郵件通知
def send_notification(subject, message, recipients=None):
    try:
        if not recipients:
            recipients = [frappe.get_value("User", {"send_system_notification": 1}, "email")]
            frappe.sendmail(
                recipients=recipients,
                subject=subject,
                message=message,
                now=True
            )
        msg = f"已發送電子郵件通知: {subject} to {recipients}"
        logger.info(msg)
        print(msg)
    except Exception as e:
        msg = f"發送電子郵件通知失敗: {e}"
        logger.error(msg)
        print(msg)

# 主執行函數
def execute():
    logger.info("開始執行採購訂單匯入...")
    print("開始執行採購訂單匯入...")
    global log_buffer
    log_buffer = StringIO()
    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        error_occurred = False
        error_messages = []

        # 確保 proceed 目錄存在
        if not os.path.exists(PROCEED_DIR):
            os.makedirs(PROCEED_DIR)
            msg = f"創建目錄: {PROCEED_DIR}"
            logger.info(msg)
            print(msg)

        # 掃描 po*.txt 檔案
        file_pattern = os.path.join(INPUT_DIR, "po*.txt")
        files = glob.glob(file_pattern)

        if not files:
            msg = f"在 {INPUT_DIR} 中未找到任何 po*.txt 檔案"
            logger.info(msg)
            print(msg)
            error_messages.append(msg)
            error_occurred = True
        else:
            for file_path in files:
                msg = f"正在處理檔案: {file_path}"
                logger.info(msg)
                print(msg)
                purchase_orders.clear()
                import_po_data(file_path)
                for po_number, po in purchase_orders.items():
                    success, msg = create_purchase_order(po)
                    if not success:
                        error_occurred = True
                        error_messages.append(msg)
                try:
                    dest_path = os.path.join(PROCEED_DIR, os.path.basename(file_path))
                    shutil.move(file_path, dest_path)
                    msg = f"檔案已移動到: {dest_path}"
                    logger.info(msg)
                    print(msg)
                except Exception as e:
                    error_occurred = True
                    msg = f"移動檔案 {file_path} 失敗: {e}"
                    logger.error(msg)
                    print(msg)
                    error_messages.append(msg)

        log_output = log_buffer.getvalue()
        subject = f"[{'error' if error_occurred else 'info'}] Purchase Order Import Result - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message = f"Import PO {'Fail' if error_occurred else 'Success'}，log:\n\n {log_output}"
        if error_occurred:
            message += "\n\n詳細錯誤:\n" + "\n".join(error_messages)
        # send_notification(subject, message)
        

@frappe.whitelist()
def reload_single_po_from_txt(po_number):
    """
    從 INPUT_DIR 找出含有此 po_number 的 po*.txt，重新載入該 PO。
    po_number 由前端 (PO 表單) 傳入。
    """
    po_number = (po_number or "").strip()
    if not po_number:
        frappe.throw("PO Number is empty.")

    # 1. 找到所有 po*.txt
    file_pattern = os.path.join(PROCEED_DIR, "po*.txt")
    files = glob.glob(file_pattern)

    if not files:
        frappe.throw(f"No po*.txt file found in {PROCEED_DIR}.")

    matched_file = None

    # 2. 掃描每個檔案，看裡面是否包含這個 po_number (01 行的欄位)
    for file_path in files:
        purchase_orders.clear()
        import_po_data(file_path)   # 這會把所有 PO 放進 purchase_orders

        if po_number in purchase_orders:
            matched_file = file_path
            break

    if not matched_file:
        frappe.throw(f"PO Number {po_number} not found in any po*.txt under {PROCEED_DIR}.")

    # 3. 用找到的檔案 + 對應的 po_number 重新建立 / 更新 PO
    po_data = purchase_orders.get(po_number)
    if not po_data:
        frappe.throw(f"PO data for {po_number} not parsed correctly from {matched_file}.")

    success, msg = create_purchase_order(po_data)
    if not success:
        frappe.throw(f"Reload PO failed: {msg}")
    
    # 取得實際 PO 名稱（可能不是 po_number 本身）
    po_name = frappe.db.get_value(PO_DOCTYPE, {"po_number": po_number}, "name")

    # 在 Activity Log / Comments 加一筆紀錄
    if po_name:
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reload PO from TXT file ({os.path.basename(matched_file)}) via manual button."
        add_activity_message(PO_DOCTYPE, po_name, comment, 'Info')
    
    return {
        "message": f"PO {po_number} reloaded from {os.path.basename(matched_file)} successfully.",
        "file": os.path.basename(matched_file)
    }