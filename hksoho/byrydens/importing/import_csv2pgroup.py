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
PRODUCT_GROUP_DOCTYPE = "Product Group"

# 從 site_config 獲取路徑，預設值作為備用
INPUT_DIR = frappe.get_site_config().get("partner_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("partner_import_proceed_dir", "/home/ftpuser/done")
LOG_FILE = frappe.get_site_config().get("pgroup_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/pgroup_import.log")
GROUP_FILE = "xpin_groups.txt"

# 設置日誌
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a', format='[%(asctime)s] %(levelname)s: %(message)s')

# 儲存 Product Group 資料結構
product_groups = {}

# 用於收集日誌訊息
log_buffer = StringIO()

# 檢查 Product Group 是否存在
def check_product_group_exists(group_id):
    return frappe.db.exists(PRODUCT_GROUP_DOCTYPE, {"group_id": group_id})

# 讀取 TXT 檔案
def import_product_group_data(file_path):
    try:
        with open(file_path, mode='r', encoding='cp1252') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                group_id = row.get('GROUPID')
                if not group_id:
                    msg = f"無效的記錄，缺少 GROUPID: {row}"
                    logger.warning(msg)
                    print(msg)
                    continue
                
                product_group_data = {
                    "group_id": group_id,
                    "description": row.get('DESCRIPTION')
                }
                product_groups[group_id] = product_group_data
    except FileNotFoundError:
        msg = f"檔案未找到: {file_path}"
        logger.error(msg)
        print(msg)
    except Exception as e:
        msg = f"處理檔案 {file_path} 時發生錯誤: {e}"
        logger.error(msg)
        print(msg)

# 創建或更新 Product Group
def create_or_update_product_group(group_data):
    group_id = group_data["group_id"]
    
    group_exists = check_product_group_exists(group_id)
    
    if group_exists:
        existing_group = frappe.get_doc(PRODUCT_GROUP_DOCTYPE, {"group_id": group_id})
        if existing_group.description == group_data["description"]:
            msg = f"Product Group {group_id} 的 description 未變更，跳過更新"
            logger.info(msg)
            print(msg)
            return False, msg
        
        group = existing_group
        msg = f"Product Group {group_id} 已存在，正在更新..."
        logger.info(msg)
        print(msg)
        action = "Updated"
    else:
        group = frappe.new_doc(PRODUCT_GROUP_DOCTYPE)
        msg = f"創建新 Product Group: {group_id}"
        logger.info(msg)
        print(msg)
        action = "Created"

    try:
        group.update({
            "group_id": group_data["group_id"],
            "description": group_data["description"]
        })
        
        group.save(ignore_permissions=True)
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Import TXT file - {action}"
        add_activity_message(PRODUCT_GROUP_DOCTYPE, group.name, comment, 'Info')
        frappe.db.commit()
        msg = f"已{action} Product Group: {group.name}"
        logger.info(msg)
        print(msg)
        return True, msg
    except Exception as e:
        msg = f"{action} Product Group {group_id} 失敗: {e}"
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
    logger.info("開始執行 Product Group 匯入...")
    print("開始執行 Product Group 匯入...")
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
        file_patterns = [os.path.join(INPUT_DIR, GROUP_FILE)]
        files_to_process = []
        for pattern in file_patterns:
            files_to_process.extend(glob.glob(pattern))

        if not files_to_process:
            msg = f"在 {INPUT_DIR} 中未找到 xpin_groups.txt 檔案"
            logger.info(msg)
            print(msg)
            error_messages.append(msg)
            error_occurred = True
        else:
            for file_path in files_to_process:
                msg = f"正在處理檔案: {file_path}"
                logger.info(msg)
                print(msg)
                product_groups.clear()
                import_product_group_data(file_path)
                for group_id, group in product_groups.items():
                    success, msg = create_or_update_product_group(group)
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
        subject = f"[{'error' if error_occurred else 'info'}] Product Group Import Result - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message = f"Import Product Group {'Fail' if error_occurred else 'Success'}，log:\n\n {log_output}"
        if error_occurred:
            message += "\n\n詳細錯誤:\n" + "\n".join(error_messages)
        # send_notification(subject, message)