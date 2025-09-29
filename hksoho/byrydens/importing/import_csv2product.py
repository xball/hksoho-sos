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
PRODUCT_DOCTYPE = "Product"
PRODUCT_GROUP_DOCTYPE = "Product Group"

# 從 site_config 獲取路徑，預設值作為備用
INPUT_DIR = frappe.get_site_config().get("partner_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("partner_import_proceed_dir", "/home/ftpuser/done")
LOG_FILE = frappe.get_site_config().get("product_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/product_import.log")
PRODUCT_FILE = "xpin_products.txt"

# 設置日誌
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a', format='[%(asctime)s] %(levelname)s: %(message)s')

# 儲存 Product 資料結構
products = {}

# 用於收集日誌訊息
log_buffer = StringIO()

# range 欄位映射
RANGE_MAPPING = {
    "1": "1 - Rydéns",
    "2": "2 - Rydéns (no re-buy)",
    "3": "3 - Components",
    "4": "4 - Semi-manufactures",
    "5": "5 - Customer items",
    "6": "6 - Mono Light Lab",
    "C1": "C1 - Cottex",
    "C2": "C2 - Cottex (no re-buy)",
    "C5": "C5 - Cottex customer Items"
}

# packaging 欄位映射
PACKAGING_MAPPING = {
    "1": "By Ry black box",
    "2": "White box w/labels",
    "3": "Dropship",
    "4": "Plasticbag w/header",
    "5": "Brown box",
    "6": "Shrink package",
    "7": "PET box",
    "8": "Blister",
    "9": "White box w/print"
}

# 格式化日期
def format_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logger.warning(f"無效的日期格式: {date_str}")
        return None

# 檢查 Product 是否存在
def check_product_exists(article_number):
    return frappe.db.exists(PRODUCT_DOCTYPE, {"article_number": article_number})

# 檢查並創建 Product Group
def validate_product_group(group_id):
    if not group_id:
        return None
    try:
        group_id = group_id.strip()
        product_group = frappe.db.get_value(PRODUCT_GROUP_DOCTYPE, {"group_id": group_id}, "name")
        if not product_group:
            # 創建新的 Product Group
            logger.info(f"Product Group 未找到: {group_id}，正在創建新記錄")
            new_group = frappe.new_doc(PRODUCT_GROUP_DOCTYPE)
            new_group.group_id = group_id
            new_group.description = group_id
            new_group.save(ignore_permissions=True)
            frappe.db.commit()
            msg = f"已創建新 Product Group: {group_id}"
            logger.info(msg)
            print(msg)
            return new_group.name
        return product_group
    except Exception as e:
        msg = f"驗證或創建 Product Group 失敗: {group_id}, 錯誤: {str(e)}"
        logger.error(msg)
        print(msg)
        return None

# 安全轉換為整數
def safe_to_int(value, default=0, article_number=None, field_name=None):
    if not value:
        return default
    try:
        return int(float(value.replace(",", "")))
    except (ValueError, TypeError):
        msg = f"無效的整數值: {value}，使用預設值 {default}"
        if article_number and field_name:
            msg += f" (Article Number: {article_number}, Field: {field_name})"
        logger.warning(msg)
        print(msg)
        return default

# 安全轉換為浮點數
def safe_to_float(value, default=0.0, article_number=None, field_name=None):
    if not value:
        return default
    try:
        return float(value.replace(",", ""))
    except (ValueError, TypeError):
        msg = f"無效的浮點數值: {value}，使用預設值 {default}"
        if article_number and field_name:
            msg += f" (Article Number: {article_number}, Field: {field_name})"
        logger.warning(msg)
        print(msg)
        return default

# 映射 range 值
def map_range_value(calctype, article_number=None):
    if not calctype:
        return None
    calctype = calctype.strip()
    mapped_value = RANGE_MAPPING.get(calctype)
    if not mapped_value:
        msg = f"無效的 CALCTYPE 值: {calctype}，設為 {calctype}"
        if article_number:
            msg += f" (Article Number: {article_number})"
        print(msg)
        return calctype
    return mapped_value

# 映射 packaging 值
def map_packaging_value(boxinfo, article_number=None):
    if not boxinfo:
        return None
    boxinfo = boxinfo.strip()
    mapped_value = PACKAGING_MAPPING.get(boxinfo)
    if not mapped_value:
        msg = f"無效的 BOXINFO 值: {boxinfo}，設為 {boxinfo}"
        if article_number:
            msg += f" (Article Number: {article_number})"
        print(msg)
        return boxinfo
    return mapped_value

# 比較欄位是否不同
def has_field_changes(existing_product, new_data):
    fields_to_compare = [
        "article_number", "article_name", "category", "customs_tariff_code",
        "minimum_order_quantity", "production_leadtime_days", "gross_width_mm_innerunit_box",
        "gross_height_mm_innerunit_box", "gross_length_mm_innerunit_box", "gross_weight_kg_innerunit_box",
        "gross_cbm_innerunit_box", "units_in_carton_pieces_per_carton", "carton_width_mm_outer_carton",
        "carton_height_mm_outer_carton", "carton_length_mm_outer_carton", "carton_weight_kg_outer_carton",
        "carton_cbm_outer_carton", "price", "currency", "designer", "range",
        "sample_article_number", "classification", "qc_required", "packaging"
    ]
    for field in fields_to_compare:
        existing_value = getattr(existing_product, field, None) or ""
        new_value = new_data.get(field, "") or ""
        if existing_value != new_value:
            logger.info(f"欄位 {field} 有變更: 原值={existing_value}, 新值={new_value}")
            return True
    return False

# 讀取 TXT 檔案
def import_product_data(file_path):
    try:
        with open(file_path, mode='r', encoding='latin1', errors='ignore') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                article_number = row.get('ARTNO')
                if not article_number:
                    msg = f"無效的記錄，缺少 ARTNO: {row}"
                    logger.warning(msg)
                    print(msg)
                    continue

                category = validate_product_group(row.get('GROUP'))
                qc_required = 1 if row.get('VENDORQC') == 'Y' else 0
                # 尺寸從 cm 轉為 mm (乘以 10)
                eawidth = safe_to_int(row.get('EAWIDTH'), default=0, article_number=article_number, field_name='EAWIDTH') * 10
                eaheight = safe_to_int(row.get('EAHEIGHT'), default=0, article_number=article_number, field_name='EAHEIGHT') * 10
                ealength = safe_to_int(row.get('EALENGTH'), default=0, article_number=article_number, field_name='EALENGTH') * 10
                ctnwidth = safe_to_int(row.get('CTNWIDTH'), default=0, article_number=article_number, field_name='CTNWIDTH') * 10
                ctnheight = safe_to_int(row.get('CTNHEIGHT'), default=0, article_number=article_number, field_name='CTNHEIGHT') * 10
                ctnlength = safe_to_int(row.get('CTNLENGTH'), default=0, article_number=article_number, field_name='CTNLENGTH') * 10

                # 處理 UPDATED 和 INSERTED
                updated_date = row.get('UPDATED')
                if not updated_date:
                    updated_date = row.get('INSERTED')
                    if updated_date:
                        msg = f"UPDATED 為空，使用 INSERTED 值: {updated_date} (Article Number: {article_number})"
                        logger.info(msg)
                        print(msg)
                    else:
                        msg = f"UPDATED 和 INSERTED 均為空，設為 None (Article Number: {article_number})"
                        logger.warning(msg)
                        print(msg)

                product_data = {
                    "article_number": article_number,
                    "article_name": row.get('ARTNAME'),
                    "category": category,
                    "customs_tariff_code": row.get('HSCODE'),
                    "minimum_order_quantity": safe_to_float(row.get('MOQ'), default=0.0, article_number=article_number, field_name='MOQ'),
                    "production_leadtime_days": safe_to_int(row.get('LEADTIME'), default=0, article_number=article_number, field_name='LEADTIME'),
                    "gross_width_mm_innerunit_box": eawidth,
                    "gross_height_mm_innerunit_box": eaheight,
                    "gross_length_mm_innerunit_box": ealength,
                    "gross_weight_kg_innerunit_box": safe_to_float(row.get('EAWEIGHT'), default=0.0, article_number=article_number, field_name='EAWEIGHT'),
                    "gross_cbm_innerunit_box": safe_to_float(row.get('EACBM'), default=0.0, article_number=article_number, field_name='EACBM'),
                    "units_in_carton_pieces_per_carton": safe_to_int(row.get('QTYPERCTN'), default=1, article_number=article_number, field_name='QTYPERCTN'),
                    "carton_width_mm_outer_carton": ctnwidth,
                    "carton_height_mm_outer_carton": ctnheight,
                    "carton_length_mm_outer_carton": ctnlength,
                    "carton_weight_kg_outer_carton": safe_to_float(row.get('CTNWEIGHT'), default=0.0, article_number=article_number, field_name='CTNWEIGHT'),
                    "carton_cbm_outer_carton": safe_to_float(row.get('CTNCBM'), default=0.0, article_number=article_number, field_name='CTNCBM'),
                    "price": safe_to_float(row.get('PRICE'), default=0.0, article_number=article_number, field_name='PRICE'),
                    "currency": row.get('CURRENCY'),
                    "designer": row.get('DESIGNER'),
                    "range": map_range_value(row.get('CALCTYPE'), article_number=article_number),
                    "sample_article_number": row.get('SAMPLEARTNO'),
                    "classification": row.get('ABCCLASS'),
                    "qc_required": qc_required,
                    "packaging": map_packaging_value(row.get('BOXINFO'), article_number=article_number),
                    "updated": updated_date
                }
                products[article_number] = product_data
        return True
    except FileNotFoundError:
        msg = f"檔案未找到: {file_path}"
        logger.error(msg)
        print(msg)
        return False
    except Exception as e:
        msg = f"處理檔案 {file_path} 時發生錯誤: {e}"
        logger.error(msg)
        print(msg)
        return False

# 創建或更新 Product
def create_or_update_product(product_data):
    article_number = product_data["article_number"]
    updated_date = product_data.pop("updated", None)  # 移除 updated 以避免存入 Doctype
    
    if updated_date:
        updated_date = format_date(updated_date)
        if not updated_date:
            msg = f"無效的 UPDATED/INSERTED 日期: {updated_date}，跳過記錄: {article_number}"
            logger.warning(msg)
            print(msg)
            return False, msg
    else:
        msg = f"缺少 UPDATED/INSERTED 日期，跳過記錄: {article_number}"
        logger.warning(msg)
        print(msg)
        return False, msg

    product_exists = check_product_exists(article_number)
    
    if product_exists:
        existing_product = frappe.get_doc(PRODUCT_DOCTYPE, {"article_number": article_number})
        # 檢查日期是否較新
        if updated_date <= existing_product.modified:
            msg = f"Product {article_number} 的 UPDATED/INSERTED 日期 ({updated_date}) 不晚於 modified 日期 ({existing_product.modified})，跳過更新"
            logger.info(msg)
            print(msg)
            return False, msg
        
        # 檢查是否有其他欄位變化
        if not has_field_changes(existing_product, product_data):
            msg = f"Product {article_number} 無欄位變更，跳過更新"
            logger.info(msg)
            print(msg)
            return False, msg
        
        product = existing_product
        changes = [f"{field}: {getattr(existing_product, field, None)} -> {product_data.get(field)}" 
                   for field in product_data if getattr(existing_product, field, None) != product_data.get(field)]
        msg = f"Product {article_number} 已存在且有欄位變更，正在更新... 變化: {', '.join(changes)}"
        logger.info(msg)
        print(msg)
        action = "Updated"
    else:
        product = frappe.new_doc(PRODUCT_DOCTYPE)
        msg = f"創建新 Product: {article_number}"
        logger.info(msg)
        print(msg)
        action = "Created"

    try:
        product.update(product_data)
        product.save(ignore_permissions=True)
        comment = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Import TXT file - {action}"
        add_activity_message(PRODUCT_DOCTYPE, product.name, comment, 'Info')
        frappe.db.commit()
        msg = f"已{action} Product: {product.name}"
        logger.info(msg)
        print(msg)
        return True, msg
    except Exception as e:
        msg = f"{action} Product {article_number} 失敗: {e}"
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
    logger.info("開始執行 Product 匯入...")
    print("開始執行 Product 匯入...")
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
        file_patterns = [os.path.join(INPUT_DIR, PRODUCT_FILE)]
        files_to_process = []
        for pattern in file_patterns:
            files_to_process.extend(glob.glob(pattern))

        if not files_to_process:
            msg = f"在 {INPUT_DIR} 中未找到 xpin_products.txt 檔案"
            logger.info(msg)
            print(msg)
            error_messages.append(msg)
            error_occurred = True
        else:
            for file_path in files_to_process:
                msg = f"正在處理檔案: {file_path}"
                logger.info(msg)
                print(msg)
                products.clear()
                import_success = import_product_data(file_path)
                if not import_success:
                    error_occurred = True
                    error_messages.append(f"檔案 {file_path} 處理失敗")
                    continue
                
                for article_number, product in products.items():
                    success, msg = create_or_update_product(product)
                    if not success:
                        error_occurred = True
                        error_messages.append(msg)
                
                # 僅在成功處理所有記錄後移動檔案
                if not error_occurred:
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
        subject = f"[{'error' if error_occurred else 'info'}] Product Import Result - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message = f"Import Product {'Fail' if error_occurred else 'Success'}，log:\n\n {log_output}"
        if error_occurred:
            message += "\n\n詳細錯誤:\n" + "\n".join(error_messages)
        #send_notification(subject, message)