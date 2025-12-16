import frappe
import os
import glob
import shutil
import csv
from datetime import datetime
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta

# 只處理最近 N 天內 UPDATED/INSERTED 的商品
DAYS_THRESHOLD = 30
CUTOFF_DATETIME = datetime.now() - timedelta(days=DAYS_THRESHOLD)


# ============================ DocType 定義 ============================
PRODUCT_DOCTYPE = "Product"
PRODUCT_GROUP_DOCTYPE = "Product Group"

# ============================ 路徑設定 ============================
INPUT_DIR = frappe.get_site_config().get("partner_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("partner_import_proceed_dir", "/home/ftpuser/done")
IMAGE_INPUT_DIR = frappe.get_site_config().get("partner_import_image_dir", "/home/ftpuser/ftp/img")
LOG_FILE = frappe.get_site_config().get("product_import_log_file", "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/product_import.log")
PRODUCT_FILE = "xpin_products.txt"

# ============================ 日誌設定 ============================
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR, filename=LOG_FILE, filemode='a',
                    format='[%(asctime)s] %(levelname)s: %(message)s')

products = {}
log_buffer = StringIO()

# ============================ 圖片副檔名支援 ============================
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP')

# ====================== 強制更新主圖旗標 ======================
# True  → 即使其他資料沒變，只要圖片不同或有新圖就強制更新 Product
# False → 只有資料或日期有變才更新（標準模式）
FORCE_UPDATE_IMAGE = False   # ← 改這一行即可控制！建議客戶補圖時開 True
# ====================== 新增：強制更新名稱旗標（這次專用）======================
FORCE_UPDATE_NAME = False   # ← 改成 True 就強制全部更新 article_name！
# ============================ Range & Packaging 對照表 ============================
RANGE_MAPPING = {
    "1": "1 - Rydéns", "2": "2 - Rydéns (no re-buy)", "3": "3 - Components",
    "4": "4 - Semi-manufactures", "5": "5 - Customer items", "6": "6 - Mono Light Lab",
    "C1": "C1 - Cottex", "C2": "C2 - Cottex (no re-buy)", "C5": "C5 - Cottex customer Items"
}

PACKAGING_MAPPING = {
    "1": "By Ry black box", "2": "White box w/labels", "3": "Dropship",
    "4": "Plasticbag w/header", "5": "Brown box", "6": "Shrink package",
    "7": "PET box", "8": "Blister", "9": "White box w/print"
}

# ============================ 工具函數 ============================
def format_date(date_str):
    if not date_str or not date_str.strip(): return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d")
    except ValueError:
        logger.warning(f"無效日期格式: {date_str}")
        return None

def check_product_exists(article_number):
    return frappe.db.exists(PRODUCT_DOCTYPE, {"article_number": article_number.strip()})

def validate_product_group(group_id):
    if not group_id: return None
    group_id = group_id.strip()
    name = frappe.db.get_value(PRODUCT_GROUP_DOCTYPE, {"group_id": group_id}, "name")
    if not name:
        doc = frappe.new_doc(PRODUCT_GROUP_DOCTYPE)
        doc.group_id = group_id
        doc.description = group_id
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        logger.info(f"新建 Product Group: {group_id}")
        return doc.name
    return name

def safe_to_int(v, d=0, art=None, f=None):
    if not v: return d
    try: return int(float(str(v).replace(",", "")))
    except: 
        logger.warning(f"轉整數失敗 {v} → {d} (ARTNO: {art}, Field: {f})")
        return d

def safe_to_float(v, d=0.0, art=None, f=None):
    if not v: return d
    try: return float(str(v).replace(",", ""))
    except: 
        logger.warning(f"轉浮點失敗 {v} → {d} (ARTNO: {art}, Field: {f})")
        return d

def map_range_value(v, art=None):
    if not v: return None
    return RANGE_MAPPING.get(v.strip(), v.strip())

def map_packaging_value(v, art=None):
    if not v: return None
    return PACKAGING_MAPPING.get(v.strip(), v.strip())

# ============================ 圖片處理（終極版：完全不怕大小寫 + 副檔名不同） ============================
def find_real_image_file(image_field_value, artno):
    """
    超強圖片搜尋引擎
    支援：
    - .JPG / .jpg / .JPEG / .jpeg / .png 等
    - TXT 寫 .JPG 但實際是 .jpg（最常見！）
    - 檔名有空白或引號
    """
    if not image_field_value:
        logger.info(f"IMAGE 欄位為空 (ARTNO: {artno})")
        return None

    raw_name = str(image_field_value).strip().strip('"').strip("'")
    if not raw_name:
        return None

    # Step 1: 直接用原始檔名找（包含副檔名）
    direct_path = os.path.join(IMAGE_INPUT_DIR, raw_name)
    if os.path.isfile(direct_path):
        logger.info(f"直接命中圖片: {direct_path}")
        return direct_path

    # Step 2: 取出檔名主體（去副檔名），強制搜尋所有常見副檔名 + 大小寫組合
    base_name = os.path.splitext(raw_name)[0]  # 去掉 .JPG
    possible_names = []

    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP']:
        possible_names.append(base_name + ext)           # S03012.jpg
        possible_names.append(base_name.lower() + ext)   # s03012.jpg
        possible_names.append(base_name.upper() + ext)   # S03012.JPG

    # 去重複
    possible_names = list(set(possible_names))

    for name in possible_names:
        full_path = os.path.join(IMAGE_INPUT_DIR, name)
        if os.path.isfile(full_path):
            logger.info(f"智慧搜尋命中: {full_path} ← 來自 IMAGE 欄位: {raw_name}")
            return full_path

    logger.info(f"完全找不到圖片: {raw_name} (ARTNO: {artno})")
    return None


# ============================ 圖片處理（正確從 IMAGE 欄位取） ============================
def get_image_path_from_image_field(image_field, artno):
    """根據 TXT 中的 IMAGE 欄位找實際檔案"""
    if not image_field or not str(image_field).strip():
        logger.info(f"IMAGE 欄位為空 (ARTNO: {artno})")
        return None

    fname = str(image_field).strip().replace('"', '').replace("'", '')
    if not fname:
        return None

    # 情況1：完整檔名（含副檔名）
    full_path = os.path.join(IMAGE_INPUT_DIR, fname)
    if os.path.isfile(full_path):
        logger.info(f"找到圖片: {full_path}")
        return full_path

    # 情況2：只有檔名無副檔名 → 嘗試常見副檔名
    for ext in IMAGE_EXTENSIONS:
        test_path = os.path.join(IMAGE_INPUT_DIR, fname + ext)
        if os.path.isfile(test_path):
            logger.info(f"找到圖片（補副檔名）: {test_path}")
            return test_path
        # 再試大小寫
        test_path2 = os.path.join(IMAGE_INPUT_DIR, fname.lower() + ext.lower())
        if os.path.isfile(test_path2):
            return test_path2

    logger.info(f"找不到圖片檔案: {fname} (ARTNO: {artno})")
    return None

def upload_image_to_frappe(image_path, product_name, article_number):
    """上傳圖片並附加到 Product"""
    if not image_path or not os.path.isfile(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            filedoc = frappe.get_doc({
                "doctype": "File",
                "file_name": os.path.basename(image_path),
                "attached_to_doctype": PRODUCT_DOCTYPE,
                "attached_to_name": product_name,   # 必須有 product.name
                "is_private": 0,
                "content": f.read()
            })
            filedoc.insert(ignore_permissions=True)
            frappe.db.commit()
            logger.info(f"圖片上傳成功: {filedoc.file_url} (ARTNO: {article_number})")
            return filedoc.file_url
    except Exception as e:
        logger.error(f"圖片上傳失敗 {image_path}: {e} (ARTNO: {article_number})")
        return None

# ============================ 欄位變更檢查 ============================
def has_field_changes1(existing, new_data):
    fields = ["article_number", "article_name", "category", "customs_tariff_code",
              "minimum_order_quantity", "production_leadtime_days", "gross_width_mm_innerunit_box",
              "gross_height_mm_innerunit_box", "gross_length_mm_innerunit_box", "gross_weight_kg_innerunit_box",
              "gross_cbm_innerunit_box", "units_in_carton_pieces_per_carton", "carton_width_mm_outer_carton",
              "carton_height_mm_outer_carton", "carton_length_mm_outer_carton", "carton_weight_kg_outer_carton",
              "carton_cbm_outer_carton", "price", "currency", "designer", "range",
              "sample_article_number", "classification", "qc_required", "packaging", "primary_image"]
    for f in fields:
        if str(getattr(existing, f, "")) != str(new_data.get(f, "")):
            return True
    return False

def has_field_changes(existing, new_data):
    fields = ["article_number", "article_name", "category", "customs_tariff_code",
              "minimum_order_quantity", "production_leadtime_days", "gross_width_mm_innerunit_box",
              "gross_height_mm_innerunit_box", "gross_length_mm_innerunit_box", "gross_weight_kg_innerunit_box",
              "gross_cbm_innerunit_box", "units_in_carton_pieces_per_carton", "carton_width_mm_outer_carton",
              "carton_height_mm_outer_carton", "carton_length_mm_outer_carton", "carton_weight_kg_outer_carton",
              "carton_cbm_outer_carton", "price", "currency", "designer", "range",
              "sample_article_number", "classification", "qc_required", "packaging"]
              # ← 故意移除 primary_image！
    for f in fields:
        if str(getattr(existing, f, "")) != str(new_data.get(f, "")):
            return True
    return False

# ============================ 讀取 TXT 檔案 ============================
def import_product_data1(file_path):
    try:
        with open(file_path, 'r', encoding='cp1252', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                artno = row.get("ARTNO", "").strip()
                if not artno:
                    logger.warning("缺少 ARTNO，跳過此列")
                    continue

                category = validate_product_group(row.get("GROUP"))

                # 尺寸 cm → mm
                eaw = safe_to_int(row.get("EAWIDTH"), 0, artno, "EAWIDTH") * 10
                eah = safe_to_int(row.get("EAHEIGHT"), 0, artno, "EAHEIGHT") * 10
                eal = safe_to_int(row.get("EALENGTH"), 0, artno, "EALENGTH") * 10
                ctw = safe_to_int(row.get("CTNWIDTH"), 0, artno, "CTNWIDTH") * 10
                cth = safe_to_int(row.get("CTNHEIGHT"), 0, artno, "CTNHEIGHT") * 10
                ctl = safe_to_int(row.get("CTNLENGTH"), 0, artno, "CTNLENGTH") * 10

                updated = row.get("UPDATED") or row.get("INSERTED")

                product_data = {
                    "article_number": artno,
                    "article_name": row.get("ARTNAME"),
                    "category": category,
                    "customs_tariff_code": row.get("HSCODE"),
                    "minimum_order_quantity": safe_to_float(row.get("MOQ"), 0.0, artno, "MOQ"),
                    "production_leadtime_days": safe_to_int(row.get("LEADTIME"), 0, artno, "LEADTIME"),
                    "gross_width_mm_innerunit_box": eaw,
                    "gross_height_mm_innerunit_box": eah,
                    "gross_length_mm_innerunit_box": eal,
                    "gross_weight_kg_innerunit_box": safe_to_float(row.get("EAWEIGHT"), 0.0, artno, "EAWEIGHT"),
                    "gross_cbm_innerunit_box": safe_to_float(row.get("EACBM"), 0.0, artno, "EACBM"),
                    "units_in_carton_pieces_per_carton": safe_to_int(row.get("QTYPERCTN"), 1, artno, "QTYPERCTN"),
                    "carton_width_mm_outer_carton": ctw,
                    "carton_height_mm_outer_carton": cth,
                    "carton_length_mm_outer_carton": ctl,
                    "carton_weight_kg_outer_carton": safe_to_float(row.get("CTNWEIGHT"), 0.0, artno, "CTNWEIGHT"),
                    "carton_cbm_outer_carton": safe_to_float(row.get("CTNCBM"), 0.0, artno, "CTNCBM"),
                    "price": safe_to_float(row.get("PRICE"), 0.0, artno, "PRICE"),
                    "currency": row.get("CURRENCY"),
                    "designer": row.get("DESIGNER"),
                    "range": map_range_value(row.get("CALCTYPE"), artno),
                    "sample_article_number": row.get("SAMPLEARTNO"),
                    "classification": row.get("ABCCLASS"),
                    "qc_required": 1 if row.get("VENDORQC") == "Y" else 0,
                    "packaging": map_packaging_value(row.get("BOXINFO"), artno),
                    "updated": updated,
                    # 暫存真實圖片路徑
                    "__image_path": find_real_image_file(row.get("IMAGE"), artno)
                }
                products[artno] = product_data
        return True
    except Exception as e:
        logger.error(f"讀取檔案失敗: {e}")
        return False

def import_product_data(file_path):
    try:
        with open(file_path, 'r', encoding='cp1252', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                artno = row.get("ARTNO", "").strip()
                if not artno:
                    logger.warning("缺少 ARTNO，跳過此列")
                    continue

                # ===== 新增：依 UPDATED / INSERTED 日期過濾 120 天前的資料 =====
                updated_raw = (row.get("UPDATED") or row.get("INSERTED") or "").strip()
                if not updated_raw:
                    logger.info(f"無 UPDATED/INSERTED 日期，跳過 {artno}")
                    continue

                try:
                    updated_dt = datetime.strptime(updated_raw, "%Y-%m-%d")
                except Exception:
                    logger.warning(f"UPDATED/INSERTED 日期格式不正確，跳過 {artno}: {updated_raw}")
                    continue

                # 只處理最近 120 天內的資料，其餘直接略過
                if updated_dt < CUTOFF_DATETIME:
                    logger.info(
                        f"{artno} UPDATED={updated_dt.date()} 早於 {DAYS_THRESHOLD} 天前 "
                        f"({CUTOFF_DATETIME.date()})，略過"
                    )
                    continue
                # ===== 120 天過濾結束，以下保留你原本的邏輯 =====

                category = validate_product_group(row.get("GROUP"))

                # 尺寸 cm → mm
                eaw = safe_to_int(row.get("EAWIDTH"), 0, artno, "EAWIDTH") * 10
                eah = safe_to_int(row.get("EAHEIGHT"), 0, artno, "EAHEIGHT") * 10
                eal = safe_to_int(row.get("EALENGTH"), 0, artno, "EALENGTH") * 10
                ctw = safe_to_int(row.get("CTNWIDTH"), 0, artno, "CTNWIDTH") * 10
                cth = safe_to_int(row.get("CTNHEIGHT"), 0, artno, "CTNHEIGHT") * 10
                ctl = safe_to_int(row.get("CTNLENGTH"), 0, artno, "CTNLENGTH") * 10

                updated = updated_raw  # 直接用剛才 parse 過的字串

                product_data = {
                    "article_number": artno,
                    "article_name": row.get("ARTNAME"),
                    "category": category,
                    "customs_tariff_code": row.get("HSCODE"),
                    "minimum_order_quantity": safe_to_float(row.get("MOQ"), 0.0, artno, "MOQ"),
                    "production_leadtime_days": safe_to_int(row.get("LEADTIME"), 0, artno, "LEADTIME"),
                    "gross_width_mm_innerunit_box": eaw,
                    "gross_height_mm_innerunit_box": eah,
                    "gross_length_mm_innerunit_box": eal,
                    "gross_weight_kg_innerunit_box": safe_to_float(row.get("EAWEIGHT"), 0.0, artno, "EAWEIGHT"),
                    "gross_cbm_innerunit_box": safe_to_float(row.get("EACBM"), 0.0, artno, "EACBM"),
                    "units_in_carton_pieces_per_carton": safe_to_int(row.get("QTYPERCTN"), 1, artno, "QTYPERCTN"),
                    "carton_width_mm_outer_carton": ctw,
                    "carton_height_mm_outer_carton": cth,
                    "carton_length_mm_outer_carton": ctl,
                    "carton_weight_kg_outer_carton": safe_to_float(row.get("CTNWEIGHT"), 0.0, artno, "CTNWEIGHT"),
                    "carton_cbm_outer_carton": safe_to_float(row.get("CTNCBM"), 0.0, artno, "CTNCBM"),
                    "price": safe_to_float(row.get("PRICE"), 0.0, artno, "PRICE"),
                    "currency": row.get("CURRENCY"),
                    "designer": row.get("DESIGNER"),
                    "range": map_range_value(row.get("CALCTYPE"), artno),
                    "sample_article_number": row.get("SAMPLEARTNO"),
                    "classification": row.get("ABCCLASS"),
                    "qc_required": 1 if row.get("VENDORQC") == "Y" else 0,
                    "packaging": map_packaging_value(row.get("BOXINFO"), artno),
                    "updated": updated,
                    "__image_path": find_real_image_file(row.get("IMAGE"), artno),
                }
                products[artno] = product_data

        return True
    except Exception as e:
        logger.error(f"讀取檔案失敗: {e}")
        return False


# ============================ 建立或更新 Product ============================


def create_or_update_product(data):
    artno = data["article_number"]
    updated_date = format_date(data.pop("updated", None))
    image_path = data.pop("__image_path", None)  # 來自 TXT 的 IMAGE 欄位

    if not updated_date:
        logger.warning(f"無有效日期，跳過 {artno}")
        return False, "無日期"

    exists = check_product_exists(artno)
    product = frappe.get_doc(PRODUCT_DOCTYPE, {"article_number": artno}) if exists else frappe.new_doc(PRODUCT_DOCTYPE)

    # ==============================================
    # 1. 判斷是否真的需要存檔
    # ==============================================
    data_changed = False          # 一般欄位是否有變
    name_changed = False          # 名稱是否真的不同（僅在強制模式下使用）
    image_needs_update = False    # 圖片是否要處理

    # --- 圖片邏輯 ---
    current_image = getattr(product, "primary_image", None) or ""

    if FORCE_UPDATE_IMAGE:
        image_needs_update = bool(image_path)  # 強制覆蓋：只要有圖就換
    else:
        image_needs_update = bool(image_path) and not current_image.strip()  # 正常：沒圖才補

    # --- 名稱強制更新模式 ---
    if FORCE_UPDATE_NAME:
        new_name = data.get("article_name", "").strip()
        old_name = (getattr(product, "article_name", "") or "").strip()
        name_changed = (new_name != old_name and new_name)  # 有差異且新名稱不為空
        # 注意：此模式下「其他欄位完全不比較」
    else:
        # 正常模式：比對所有欄位（不含 primary_image）
        data_changed = not exists or has_field_changes(product, data)
        name_changed = False  # 不特別處理

    # 最終是否需要 save？
    need_save = data_changed or name_changed or image_needs_update

    if not need_save:
        logger.info(f"無任何變更需求，跳過 {artno}")
        return False, "無變更"

    # ==============================================
    # 2. 開始更新
    # ==============================================
    try:
        # --- 只更新真正需要的部分 ---
        if FORCE_UPDATE_NAME and name_changed:
            # 極簡模式：只改名稱，其他完全不碰
            product.article_name = new_name
            logger.info(f"強制更新名稱 → {artno}: 『{old_name}』→『{new_name}』")
        else:
            # 正常模式：更新所有變動欄位
            product.update(data)
            if not exists:
                logger.info(f"新建 Product {artno}")

        product.save(ignore_permissions=True)

        # --- 圖片處理 ---
        if image_needs_update and image_path:
            new_url = upload_image_to_frappe(image_path, product.name, artno)
            if new_url:
                product.primary_image = new_url
                product.save(ignore_permissions=True)
                action = "強制覆蓋主圖" if FORCE_UPDATE_IMAGE else "補上主圖（原無圖）"
                logger.info(f"{action} → {artno}: {new_url}")

        # --- Comment 記錄（精準描述本次做了什麼）---
        parts = ["匯入 TXT"]
        if not exists:
            parts.append("新建")
        elif FORCE_UPDATE_NAME and name_changed:
            parts.append("僅更新名稱")
        elif data_changed:
            parts.append("更新資料")

        if image_needs_update and image_path:
            parts.append("強制覆蓋主圖" if FORCE_UPDATE_IMAGE else "補上主圖")

        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": PRODUCT_DOCTYPE,
            "reference_name": product.name,
            "content": f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {'，'.join(parts)}"
        }).insert(ignore_permissions=True)

        #frappe.db.commit()
        logger.info(f"成功處理 {artno} ({product.name})")
        return True, "成功"

    except Exception as e:
        logger.error(f"處理失敗 {artno}: {e}")
        return False, str(e)
# ============================ 主函數 ============================
def execute():
    global log_buffer
    log_buffer = StringIO()
    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        logger.info("=== 開始 Product + 主圖匯入 ===")
        os.makedirs(PROCEED_DIR, exist_ok=True)
        os.makedirs(IMAGE_INPUT_DIR, exist_ok=True)

        file_path = os.path.join(INPUT_DIR, PRODUCT_FILE)
        if not os.path.isfile(file_path):
            logger.error(f"找不到檔案: {file_path}")
            return

        if import_product_data(file_path):
            for artno, data in products.items():
                create_or_update_product(data)

            dest = os.path.join(PROCEED_DIR, PRODUCT_FILE)
            shutil.move(file_path, dest)
            logger.info(f"匯入完成，檔案移至: {dest}")
        logger.info("=== 匯入結束 ===")