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

# DocType 定義
PO_DOCTYPE = "Purchase Order2"
PO_ITEM_DOCTYPE = "Purchase Order Item2"

# 從 site_config 獲取路徑，預設值作為備用
INPUT_DIR = frappe.get_site_config().get("po_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("po_import_proceed_dir", "/home/ftpuser/done")
LOG_FILE = frappe.get_site_config().get("po_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/po_import.log")

# 設置日誌
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a', format='[%(asctime)s] %(levelname)s: %(message)s')

# 儲存 PO 和 PO 項目的資料結構
purchase_orders = {}

# 用於收集日誌訊息
log_buffer = StringIO()

# 格式化日期
def format_date(date_str):
    if not date_str:
        return None
    try:
        # 假設 CSV 日期格式為 DD/MM/YYYY，根據實際格式調整
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
                        "requested_qty": int(row[4]) if row[4] else 0,
                        "article_name": row[6],
                        "supplier_art_number": row[7],
                        "supplier_selling_price": float(row[8]) if row[8] else 0,
                        "supplier_selling_price_unit": row[9],
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
    purchaser = validate_link_field("User", "name_in_pyramid", po_data["purchaser"])
    responsible = validate_link_field("User", "name_in_pyramid", po_data["responsible"])
    order_type = "Standard" if po_data["need_sample"] == "N" else "Sample"
    delivery_terms = validate_link_field("Delivery Term", "name", po_data["delivery_terms"])
    payment_terms = validate_link_field("Payment Term", "code", po_data["payment_terms"])
    delivery_mode = "BY BOAT" if po_data["delivery_mode"] == "1" else "BY AIR"

    if not supplier_code:
        msg = f"無效的 supplier_code: {po_data['supplier_code']}，無法創建或更新採購訂單"
        logger.error(msg)
        print(msg)
        return False, msg

    # 載入或創建 PO
    if po_exists:
        po = frappe.get_doc(PO_DOCTYPE, {"po_number": po_data["po_number"]})
        msg = f"採購訂單 {po_data['po_number']} 已存在，正在更新..."
        logger.info(msg)
        print(msg)
        action = "Updated"
    else:
        po = frappe.new_doc(PO_DOCTYPE)
        msg = f"創建新採購訂單: {po_data['po_number']}"
        logger.info(msg)
        print(msg)
        action = "Created"

    # 更新主表欄位
    po.po_number = po_data["po_number"]
    po.supplier = supplier_code
    po.purchaser = purchaser
    po.po_placed = (po_data["po_placed"])
    po.payment_terms = payment_terms
    po.delivery_mode = delivery_mode
    po.delivery_terms = delivery_terms
    po.conversion_rate = 1.0
    po.delivery_address = po_data["delivery_address"]
    po.requested_forwarder = po_data["requested_forwarder"]
    po.responsible = responsible
    po.order_type = order_type
    po.purpose = po_data["purpose"]

    # 處理子表
    existing_items = {item.line: item for item in po.po_items if item.line} if po_exists else {}
    new_items = []
    for item in po_data["items"]:
        article_number = validate_link_field("Product", "article_number", item["article_number"])
        if not article_number:
            msg = f"無效的 article_number: {item['article_number']}，跳過項目"
            logger.warning(msg)
            print(msg)
            continue

        item_data = {
            "article_number": article_number,
            "requested_qty": item["requested_qty"],
            "supplier_selling_price": item["supplier_selling_price"],
            "supplier_selling_price_unit": item["supplier_selling_price_unit"],
            "article_name": item["article_name"],
            "short_description": "\n".join(item["short_description"]),
            "requested_finish_date": (item["requested_finish_date"]),
            "requested_eta": (item["requested_eta"]),
            "line": item["line"],
            "supplier_art_number": item["supplier_art_number"]
        }

        if po_exists and item["line"] in existing_items:
            existing_item = existing_items[item["line"]]
            existing_item.update(item_data)
            new_items.append(existing_item.as_dict())
        else:
            new_items.append(item_data)

    po.set("po_items", new_items)

    try:
        po.save(ignore_permissions=True)
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Import CSV file - {action}"
        add_activity_message(PO_DOCTYPE, po.name, comment, 'Info')
        frappe.db.commit()
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
        send_notification(subject, message)