import frappe
import os
import glob
import shutil
import csv
from datetime import datetime, date
from frappe.desk.form.utils import add_comment
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# DocType 定義
CURRENCY_RATE_DOCTYPE = "Currency Rate"

# 從 site_config 獲取路徑，預設值作為備用
INPUT_DIR = frappe.get_site_config().get("currency_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("currency_import_proceed_dir", "/home/ftpuser/done")
LOG_FILE = frappe.get_site_config().get("currency_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/currency_import.log")
CURRENCY_FILE = "xpin_currency.txt"

# 設置日誌
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a', format='[%(asctime)s] %(levelname)s: %(message)s')

# 儲存 Currency Rate 資料結構
currency_rates = {}

# 用於收集日誌訊息
log_buffer = StringIO()

# 格式化日期
def format_date(date_str):
    if not date_str:
        return date.today().strftime("%Y-%m-%d")
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        logger.warning(f"無效的日期格式: {date_str}，使用當前日期")
        return date.today().strftime("%Y-%m-%d")

# 檢查記錄是否存在
def check_exists(doctype, filters):
    return frappe.db.exists(doctype, filters)

# 讀取 Currency Rate 檔案
def import_currency_data(file_path):
    try:
        with open(file_path, mode='r', encoding='cp1252') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                currency = row.get('CODE')
                if not currency:
                    msg = f"無效的記錄，缺少 CODE: {row}"
                    logger.warning(msg)
                    print(msg)
                    continue
                try:
                    rate = float(row.get('RATE')) if row.get('RATE') else None
                except (ValueError, TypeError):
                    msg = f"無效的 RATE 格式: {row.get('RATE')}，跳過記錄: {currency}"
                    logger.warning(msg)
                    print(msg)
                    continue
                
                currency_data = {
                    "code": currency,
                    "rate": rate,
                    "rate_date": format_date(row.get('RATEDATE'))
                }
                currency_rates[currency + "-" + currency_data["rate_date"]] = currency_data
    except FileNotFoundError:
        msg = f"檔案未找到: {file_path}"
        logger.error(msg)
        print(msg)
    except Exception as e:
        msg = f"處理檔案 {file_path} 時發生錯誤: {e}"
        logger.error(msg)
        print(msg)

# 創建 Currency Rate
def create_currency_rate(currency_data):
    currency = currency_data["code"]
    rate_date = currency_data["rate_date"]
    
    # 檢查是否已存在完全相同的記錄
    if check_exists(CURRENCY_RATE_DOCTYPE, {
        "code": currency,
        "rate": currency_data["rate"],
        "rate_date": rate_date
    }):
        msg = f"Currency Rate 已存在: {currency} 在 {rate_date} 的匯率 {currency_data['rate']}，跳過"
        logger.info(msg)
        print(msg)
        return False, msg

    try:
        currency_rate = frappe.new_doc(CURRENCY_RATE_DOCTYPE)
        currency_rate.update({
            "code": currency,
            "rate": currency_data["rate"],
            "rate_date": rate_date
        })
        currency_rate.save(ignore_permissions=True)
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Import TXT file - Created"
        add_activity_message(CURRENCY_RATE_DOCTYPE, currency_rate.name, comment, 'Info')
        frappe.db.commit()
        msg = f"已創建 Currency Rate: {currency} 在 {rate_date}"
        logger.info(msg)
        print(msg)
        return True, msg
    except Exception as e:
        msg = f"創建 Currency Rate {currency} 在 {rate_date} 失敗: {e}"
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
    logger.info("開始執行 Currency Rate 匯入...")
    print("開始執行 Currency Rate 匯入...")
    global log_buffer
    log_buffer = StringIO()
    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        error_occurred = False
        error_messages = []

        # 確保 proceed 目錄存在
        if not os.path.exists(PROCEED_DIR):
            try:
                os.makedirs(PROCEED_DIR)
                msg = f"創建目錄: {PROCEED_DIR}"
                logger.info(msg)
                print(msg)
            except Exception as e:
                msg = f"創建目錄 {PROCEED_DIR} 失敗: {e}"
                logger.error(msg)
                print(msg)
                error_messages.append(msg)
                error_occurred = True

        # 定義要處理的文件模式
        file_patterns = [
            os.path.join(INPUT_DIR, CURRENCY_FILE)
        ]

        files_to_process = []
        for pattern in file_patterns:
            files_to_process.extend(glob.glob(pattern))

        if not files_to_process:
            msg = f"在 {INPUT_DIR} 中未找到 xpin_currency.txt 檔案"
            logger.info(msg)
            print(msg)
            error_messages.append(msg)
            error_occurred = True
        else:
            for file_path in files_to_process:
                msg = f"正在處理檔案: {file_path} (data_type: Currency Rate)"
                logger.info(msg)
                print(msg)
                currency_rates.clear()
                import_currency_data(file_path)
                for key, currency_data in currency_rates.items():
                    success, msg = create_currency_rate(currency_data)
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
                    msg = f"移動檔案 {file_path} 到 {dest_path} 失敗: {e}"
                    logger.error(msg)
                    print(msg)
                    error_messages.append(msg)

        log_output = log_buffer.getvalue()
        subject = f"[{'error' if error_occurred else 'info'}] Currency Import Result - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message = f"Import Currency {'Fail' if error_occurred else 'Success'}，log:\n\n {log_output}"
        if error_occurred:
            message += "\n\n詳細錯誤:\n" + "\n".join(error_messages)
        # send_notification(subject, message)