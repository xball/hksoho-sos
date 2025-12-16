import frappe
import os
import glob
import shutil
import csv
from datetime import datetime
from frappe.desk.form.utils import add_comment
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# DocType 定義
PARTNER_DOCTYPE = "Partner"
PAYMENT_TERM_DOCTYPE = "Payment Term"

# 從 site_config 獲取路徑，預設值作為備用
INPUT_DIR = frappe.get_site_config().get("partner_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("partner_import_proceed_dir", "/home/ftpuser/done")
LOG_FILE = frappe.get_site_config().get("partner_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/partner_import.log")
FORWARDER_FILE = "xpin_forwarder.txt"
SUPPLIER_FILE = "xpin_supplier.txt"
CUSTOMER_FILE = "xpin_customer.txt"

# 設置日誌
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a', format='[%(asctime)s] %(levelname)s: %(message)s')

# 儲存 Partner 資料結構
partners = {}

# 用於收集日誌訊息
log_buffer = StringIO()

def get_effective_date(partner_data):
    # UPDATED 優先，無效則用 INSERTED
    updated = partner_data.get("updated")
    inserted = partner_data.get("inserted")

    # partner_data 裡的 updated/inserted 目前是 format_date 後的 yyyy-mm-dd 或 None
    return updated or inserted

# 格式化日期
def format_date(date_str):
    if not date_str:
        return None
    try:
        # 假設 TXT 日期格式為 YYYY-MM-DD
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        logger.warning(f"無效的日期格式: {date_str}")
        return None

# 檢查 Partner 是否存在
def check_partner_exists(code):
    return frappe.db.exists(PARTNER_DOCTYPE, {"partner_id": code})

# 檢查 Payment Term 是否存在
def validate_payment_term(paytermcode):
    if not paytermcode:
        return None
    try:
        # 清理 PAYTERMCODE，去除多餘空格
        paytermcode = paytermcode.strip()
        # 檢查 Payment Term 是否存在
        payment_term = frappe.db.get_value(PAYMENT_TERM_DOCTYPE, {"code": paytermcode}, "name")
        if not payment_term:
            logger.warning(f"Payment Term 未找到: {paytermcode}")
            return None
        return payment_term
    except Exception as e:
        logger.warning(f"驗證 PAYTERMCODE 失敗: {paytermcode}, 錯誤: {str(e)}")
        return None

# 根據文件名設置 partner_type
def get_partner_type(filename):
    if FORWARDER_FILE in filename:
        return "Transporter"
    elif SUPPLIER_FILE in filename:
        return "Supplier"
    elif CUSTOMER_FILE in filename:
        return "Customer"
    return None

# 讀取 TXT 檔案
def import_partner_data(file_path, partner_type):
    try:
        with open(file_path, mode='r', encoding='cp1252') as file:
            reader = csv.DictReader(file, delimiter='\t')  # 使用製表符作為分隔符
            for row in reader:
                code = row.get('CODE')
                if not code:
                    msg = f"無效的記錄，缺少 CODE: {row}"
                    logger.warning(msg)
                    print(msg)
                    continue

                address_parts = [row.get('ADDRESS1'), row.get('ADDRESS2'), row.get('ADDRESS3')]
                address = ", ".join(part for part in address_parts if part)
                payterm = validate_payment_term(row.get('PAYTERMCODE'))

                partner_data = {
                    "partner_id": code,
                    "partner_name": row.get('NAME'),
                    "address": address,
                    "postal_code": row.get('POSTALCODE'),
                    "city": row.get('CITY'),
                    "stateregion": row.get('REGION'),
                    "country": row.get('COUNTRYID'),
                    "phone_number": row.get('PHONE'),
                    "fax_number": row.get('FAX'),
                    "email_address": row.get('EMAIL'),
                    "website": row.get('WEBSITE'),
                    "currency": row.get('CURRENCY'),
                    "contact_name": row.get('CNAME'),
                    "contact_title": row.get('CTITLE'),
                    "contact_email": row.get('CEMAIL'),
                    "contact_phone": row.get('CPHONE'),
                    "contact_mobile": row.get('CMOBILE'),
                    "payment_term": payterm,
                    "incotermcode": row.get('INCOTERMCODE'),
                    "default_port": row.get('POLCODE') if row.get('POLCODE') else row.get('PODCODE'),
                    "inserted": format_date(row.get('INSERTED')),
                    "updated": format_date(row.get('UPDATED')),
                    "partner_type": partner_type
                }
                partners[code] = partner_data
    except FileNotFoundError:
        msg = f"檔案未找到: {file_path}"
        logger.error(msg)
        print(msg)
    except Exception as e:
        msg = f"處理檔案 {file_path} 時發生錯誤: {e}"
        logger.error(msg)
        print(msg)

# 比較欄位是否不同
def has_field_changes(existing_partner, new_data):
    fields_to_compare = [
        "partner_id", "partner_name", "address", "postal_code", "city", "stateregion",
        "country", "phone_number", "fax_number", "email_address", "website", "currency",
        "contact_name", "contact_title", "contact_email", "contact_phone", "contact_mobile",
        "payment_term", "incotermcode", "default_port", "partner_type"
    ]
    for field in fields_to_compare:
        existing_value = getattr(existing_partner, field, None) or ""
        new_value = new_data.get(field, "") or ""
        if existing_value != new_value:
            logger.info(f"欄位 {field} 有變更: 原值={existing_value}, 新值={new_value}")
            return True
    return False

# 創建或更新 Partner
def create_or_update_partner(partner_data):
    code = partner_data["partner_id"]
    # updated_date = partner_data["updated"]
    updated_date = get_effective_date(partner_data)
    
    if not updated_date:
        msg = f"UPDATED/INSERTED 日期都無效，跳過記錄: {code}"
        logger.warning(msg)
        print(msg)
        return False, msg    

    # if not updated_date:
    #     msg = f"無效的 UPDATED 日期，跳過記錄: {code}"
    #     logger.warning(msg)
    #     print(msg)
    #     return False, msg

    try:
        updated_date = datetime.strptime(updated_date, "%Y-%m-%d")
    except ValueError:
        msg = f"無效的 UPDATED 日期格式: {updated_date}, 跳過記錄: {code}"
        logger.warning(msg)
        print(msg)
        return False, msg

    partner_exists = check_partner_exists(code)
    
    if partner_exists:
        # 檢查現有記錄的 modified 日期
        existing_partner = frappe.get_doc(PARTNER_DOCTYPE, {"partner_id": code})
        if updated_date <= existing_partner.modified:
            msg = f"Partner {code} 的 UPDATED 日期 ({updated_date}) 不晚於 modified 日期 ({existing_partner.modified})，跳過更新"
            logger.info(msg)
            print(msg)
            return False, msg
        
        # 檢查欄位是否不同
        if not has_field_changes(existing_partner, partner_data):
            msg = f"Partner {code} 無欄位變更，跳過更新"
            logger.info(msg)
            print(msg)
            return False, msg
        
        partner = existing_partner
        msg = f"Partner {code} 已存在且有欄位變更，正在更新..."
        logger.info(msg)
        print(msg)
        action = "Updated"
    else:
        partner = frappe.new_doc(PARTNER_DOCTYPE)
        msg = f"創建新 Partner: {code}"
        logger.info(msg)
        print(msg)
        action = "Created"

    # 更新欄位
    partner.update({
        "partner_id": partner_data["partner_id"],
        "partner_name": partner_data["partner_name"],
        "address": partner_data["address"],
        "postal_code": partner_data["postal_code"],
        "city": partner_data["city"],
        "stateregion": partner_data["stateregion"],
        "country": partner_data["country"],
        "phone_number": partner_data["phone_number"],
        "fax_number": partner_data["fax_number"],
        "email_address": partner_data["email_address"],
        "website": partner_data["website"],
        "currency": partner_data["currency"],
        "contact_name": partner_data["contact_name"],
        "contact_title": partner_data["contact_title"],
        "contact_email": partner_data["contact_email"],
        "contact_phone": partner_data["contact_phone"],
        "contact_mobile": partner_data["contact_mobile"],
        "payment_term": partner_data["payment_term"],
        "incotermcode": partner_data["incotermcode"],
        "default_port": partner_data["default_port"],
        "partner_type": partner_data["partner_type"]
    })
    
    try:
        partner.save(ignore_permissions=True)
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Import TXT file - {action}"
        add_activity_message(PARTNER_DOCTYPE, partner.name, comment, 'Info')
        frappe.db.commit()
        msg = f"已{action} Partner: {partner.name}"
        logger.info(msg)
        print(msg)
        return True, msg
    except Exception as e:
        msg = f"{action} Partner {code} 失敗: {e}"
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
        if recipients:
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
    logger.info("開始執行 Partner 匯入...")
    print("開始執行 Partner 匯入...")
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

        # 定義要處理的文件模式
        file_patterns = [
            os.path.join(INPUT_DIR, FORWARDER_FILE),
            os.path.join(INPUT_DIR, SUPPLIER_FILE),
            os.path.join(INPUT_DIR, CUSTOMER_FILE)
        ]

        files_to_process = []
        for pattern in file_patterns:
            files_to_process.extend(glob.glob(pattern))

        if not files_to_process:
            msg = f"在 {INPUT_DIR} 中未找到任何 xpin_*.txt 檔案"
            logger.info(msg)
            print(msg)
            error_messages.append(msg)
            error_occurred = True
        else:
            for file_path in files_to_process:
                partner_type = get_partner_type(os.path.basename(file_path))
                if not partner_type:
                    msg = f"無效的文件名: {file_path}，無法確定 partner_type"
                    logger.warning(msg)
                    print(msg)
                    error_messages.append(msg)
                    error_occurred = True
                    continue

                msg = f"正在處理檔案: {file_path} (partner_type: {partner_type})"
                logger.info(msg)
                print(msg)
                partners.clear()
                import_partner_data(file_path, partner_type)
                for code, partner in partners.items():
                    success, msg = create_or_update_partner(partner)
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
        subject = f"[{'error' if error_occurred else 'info'}] Partner Import Result - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message = f"Import Partner {'Fail' if error_occurred else 'Success'}，log:\n\n {log_output}"
        if error_occurred:
            message += "\n\n詳細錯誤:\n" + "\n".join(error_messages)
        # send_notification(subject, message)