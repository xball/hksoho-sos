import frappe
import os
import shutil
import csv
from datetime import datetime, timedelta
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

from tenacity import sleep


# ====================== 強制更新主圖旗標 ======================
# True  → 即使其他資料沒變，只要圖片不同或有新圖就強制更新 Product
# False → 只有資料或日期有變才更新（標準模式）
FORCE_UPDATE_IMAGE = False   # ← 改這一行即可控制！建議客戶補圖時開 True

# ====================== 強制更新名稱旗標（這次專用）======================
FORCE_UPDATE_NAME = False    # ← 改成 True 就強制全部更新 article_name！

# 只處理最近 N 天內 UPDATED/INSERTED 的商品
DAYS_THRESHOLD = 1
CUTOFF_DATETIME = datetime.now() - timedelta(days=DAYS_THRESHOLD)

# ============================ DocType 定義 ============================
PRODUCT_DOCTYPE = "Product"
PRODUCT_GROUP_DOCTYPE = "Product Group"

# ============================ 路徑設定 ============================
INPUT_DIR = frappe.get_site_config().get("partner_import_input_dir", "/home/ftpuser/ftp")
PROCEED_DIR = frappe.get_site_config().get("partner_import_proceed_dir", "/home/ftpuser/done")
IMAGE_INPUT_DIR = frappe.get_site_config().get("partner_import_image_dir", "/home/ftpuser/ftp/img")
LOG_FILE = frappe.get_site_config().get(
    "product_import_log_file",
    "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/product_import.log"
)
PRODUCT_FILE = "xpin_products.txt"

# ============================ 日誌設定 ============================
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.WARNING, # 預設 WARNING，實際記錄內容由 logger.info()/warning()/error() 控制
    filename=LOG_FILE,
    filemode='a',
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

products = {}
log_buffer = StringIO()

# ============================ 圖片副檔名支援 ============================
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP')

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

# ============================ 欄位型別（用於比對正規化） ============================
# 目的：避免 "0" vs "0.0"、None vs "" 造成每小時都判定有變
FIELD_TYPES = {
    # 字串型
    "article_number": "str",
    "article_name": "str",
    "customs_tariff_code": "str",
    "currency": "str",
    "designer": "str",
    "range": "str",
    "sample_article_number": "str",
    "classification": "str",
    "packaging": "str",
    "category": "link",  # 其實都當字串處理

    # 整數型
    "production_leadtime_days": "int",
    "gross_width_mm_innerunit_box": "int",
    "gross_height_mm_innerunit_box": "int",
    "gross_length_mm_innerunit_box": "int",
    "units_in_carton_pieces_per_carton": "int",
    "carton_width_mm_outer_carton": "int",
    "carton_height_mm_outer_carton": "int",
    "carton_length_mm_outer_carton": "int",
    "qc_required": "int",

    # 浮點/金額型
    "minimum_order_quantity": "float",
    "gross_weight_kg_innerunit_box": "float",
    "gross_cbm_innerunit_box": "float",
    "carton_weight_kg_outer_carton": "float",
    "carton_cbm_outer_carton": "float",
    "price": "float",
}

COMPARE_FIELDS = [
    "article_number", "article_name", "category", "customs_tariff_code",
    "minimum_order_quantity", "production_leadtime_days",
    "gross_width_mm_innerunit_box", "gross_height_mm_innerunit_box", "gross_length_mm_innerunit_box",
    "gross_weight_kg_innerunit_box", "gross_cbm_innerunit_box",
    "units_in_carton_pieces_per_carton",
    "carton_width_mm_outer_carton", "carton_height_mm_outer_carton", "carton_length_mm_outer_carton",
    "carton_weight_kg_outer_carton", "carton_cbm_outer_carton",
    "price", "currency", "designer", "range",
    "sample_article_number", "classification", "qc_required", "packaging"
    # 注意：故意唔比較 primary_image（你原本設計）
]

# ============================ 工具函數 ============================
def format_date(date_str):
    if not date_str or not str(date_str).strip():
        return None
    try:
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
    except ValueError:
        logger.warning(f"無效日期格式: {date_str}")
        return None


def check_product_exists(article_number):
    return frappe.db.exists(PRODUCT_DOCTYPE, {"article_number": str(article_number).strip()})


def validate_product_group(group_id):
    if not group_id:
        return None
    group_id = str(group_id).strip()
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
    if v is None:
        return d
    s = str(v).strip()
    if not s:
        return d
    try:
        return int(float(s.replace(",", "")))
    except Exception:
        logger.warning(f"轉整數失敗 {v} → {d} (ARTNO: {art}, Field: {f})")
        return d


def safe_to_float(v, d=0.0, art=None, f=None):
    if v is None:
        return d
    s = str(v).strip()
    if not s:
        return d
    try:
        return float(s.replace(",", ""))
    except Exception:
        logger.warning(f"轉浮點失敗 {v} → {d} (ARTNO: {art}, Field: {f})")
        return d


def map_range_value(v, art=None):
    if not v:
        return None
    return RANGE_MAPPING.get(str(v).strip(), str(v).strip())


def map_packaging_value(v, art=None):
    if not v:
        return None
    return PACKAGING_MAPPING.get(str(v).strip(), str(v).strip())


def normalize_value(fieldname, value):
    """將舊值/新值正規化後再比較，避免假變更。"""
    ftype = FIELD_TYPES.get(fieldname, "str")

    if value is None:
        return None

    if ftype in ("str", "link"):
        s = str(value).strip()
        return s if s else None

    if ftype == "int":
        try:
            # 有啲可能係 Decimal / "10.0"
            return int(float(str(value).replace(",", "").strip()))
        except Exception:
            return None

    if ftype == "float":
        try:
            # 重要：round 避免 0.30000000004 之類
            return round(float(str(value).replace(",", "").strip()), 6)
        except Exception:
            return None

    # fallback
    s = str(value).strip()
    return s if s else None


def diff_fields(existing_doc, new_data):
    """回傳 (has_change, diff_list)。diff_list 係 [(field, old, new), ...]"""
    diffs = []
    for f in COMPARE_FIELDS:
        old_v = normalize_value(f, existing_doc.get(f))
        new_v = normalize_value(f, new_data.get(f))
        if old_v != new_v:
            diffs.append((f, old_v, new_v))
    return (len(diffs) > 0), diffs


# ============================ 圖片處理（完全不怕大小寫 + 副檔名不同） ============================
def find_real_image_file(image_field_value, artno):
    if not image_field_value:
        logger.info(f"IMAGE 欄位為空 (ARTNO: {artno})")
        return None

    raw_name = str(image_field_value).strip().strip('"').strip("'")
    if not raw_name:
        return None

    direct_path = os.path.join(IMAGE_INPUT_DIR, raw_name)
    if os.path.isfile(direct_path):
        logger.info(f"直接命中圖片: {direct_path}")
        return direct_path

    base_name = os.path.splitext(raw_name)[0]
    possible_names = set()

    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP']:
        possible_names.add(base_name + ext)
        possible_names.add(base_name.lower() + ext)
        possible_names.add(base_name.upper() + ext)

    for name in possible_names:
        full_path = os.path.join(IMAGE_INPUT_DIR, name)
        if os.path.isfile(full_path):
            logger.info(f"智慧搜尋命中: {full_path} ← 來自 IMAGE 欄位: {raw_name}")
            return full_path

    logger.info(f"完全找不到圖片: {raw_name} (ARTNO: {artno})")
    return None


def upload_image_to_frappe(image_path, product_name, article_number):
    if not image_path or not os.path.isfile(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            filedoc = frappe.get_doc({
                "doctype": "File",
                "file_name": os.path.basename(image_path),
                "attached_to_doctype": PRODUCT_DOCTYPE,
                "attached_to_name": product_name,
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


# ============================ 讀取 TXT 檔案 ============================
def import_product_data(file_path):
    try:
        with open(file_path, 'r', encoding='cp1252', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                artno = (row.get("ARTNO", "") or "").strip()
                if not artno:
                    logger.warning("缺少 ARTNO，跳過此列")
                    continue

                updated_raw = (row.get("UPDATED") or row.get("INSERTED") or "").strip()
                if not updated_raw:
                    logger.info(f"無 UPDATED/INSERTED 日期，跳過 {artno}")
                    continue

                try:
                    updated_dt = datetime.strptime(updated_raw, "%Y-%m-%d")
                except Exception:
                    logger.warning(f"UPDATED/INSERTED 日期格式不正確，跳過 {artno}: {updated_raw}")
                    continue

                if updated_dt < CUTOFF_DATETIME and FORCE_UPDATE_IMAGE== False and FORCE_UPDATE_NAME == False:
                    logger.info(
                        f"{artno} UPDATED={updated_dt.date()} 早於 {DAYS_THRESHOLD} 天前 "
                        f"({CUTOFF_DATETIME.date()})，略過"
                    )
                    continue

                category = validate_product_group(row.get("GROUP"))

                # 尺寸 cm → mm
                eaw = safe_to_int(row.get("EAWIDTH"), 0, artno, "EAWIDTH") * 10
                eah = safe_to_int(row.get("EAHEIGHT"), 0, artno, "EAHEIGHT") * 10
                eal = safe_to_int(row.get("EALENGTH"), 0, artno, "EALENGTH") * 10
                ctw = safe_to_int(row.get("CTNWIDTH"), 0, artno, "CTNWIDTH") * 10
                cth = safe_to_int(row.get("CTNHEIGHT"), 0, artno, "CTNHEIGHT") * 10
                ctl = safe_to_int(row.get("CTNLENGTH"), 0, artno, "CTNLENGTH") * 10

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
                    "barcode": map_packaging_value(row.get("BARCODE"), artno),
                    # 控制用
                    "updated": updated_raw,
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
    image_path = data.pop("__image_path", None)

    if not updated_date:
        logger.warning(f"無有效日期，跳過 {artno}")
        return False, "無日期"

    exists = check_product_exists(artno)
    product = frappe.get_doc(PRODUCT_DOCTYPE, {"article_number": artno}) if exists else frappe.new_doc(PRODUCT_DOCTYPE)

    # 1) 圖片判斷
    current_image = (getattr(product, "primary_image", None) or "").strip()
    if FORCE_UPDATE_IMAGE :
        image_needs_update = bool(image_path) and (not current_image)
    else:
        image_needs_update = bool(image_path) and (not current_image)

    # 2) 判斷是否要更新（並產生 diff）
    data_changed = False
    diffs = []

    if FORCE_UPDATE_NAME:
        new_name = (data.get("article_name") or "").strip()
        old_name = (getattr(product, "article_name", "") or "").strip()
        name_changed = bool(new_name) and (new_name != old_name)
        need_save = (not exists) or name_changed or image_needs_update

        if name_changed:
            diffs = [("article_name", old_name or None, new_name or None)]
        elif not exists:
            diffs = [("NEW", None, "new doc")]

    else:
        if not exists:
            data_changed = True
            diffs = [("NEW", None, "new doc")]
        else:
            data_changed, diffs = diff_fields(product, data)

        need_save = data_changed or image_needs_update

    if not need_save:
        logger.info(f"無任何變更需求，跳過 {artno}")
        return False, "無變更"

    # 3) 實際更新
    try:
        if FORCE_UPDATE_NAME:
            if not exists:
                # 新建時，仍要寫入全部欄位
                product.update(data)
            else:
                if diffs and diffs[0][0] == "article_name":
                    product.article_name = diffs[0][2]
        else:
            product.update(data)

        product.save(ignore_permissions=True)

        # 4) 圖片處理
        if image_needs_update and image_path:
            new_url = upload_image_to_frappe(image_path, product.name, artno)
            if new_url:
                product.primary_image = new_url
                product.save(ignore_permissions=True)
                if FORCE_UPDATE_IMAGE:
                    diffs.append(("primary_image", current_image or None, new_url))
                else:
                    diffs.append(("primary_image", None if not current_image else current_image, new_url))

        # 5) 插入 Comment（Timeline/Activity）
        # 把 diffs 變成易讀字串
        diff_lines = []
        for f, old_v, new_v in diffs:
            diff_lines.append(f"{f}: {old_v} → {new_v}")

        parts = ["匯入 TXT"]
        if not exists:
            parts.append("新建")
        elif FORCE_UPDATE_NAME and any(d[0] == "article_name" for d in diffs):
            parts.append("僅更新名稱")
        elif data_changed or (exists and diffs):
            parts.append("更新資料")

        if image_needs_update and image_path:
            parts.append("強制覆蓋主圖" if FORCE_UPDATE_IMAGE else "補上主圖")

        content = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {'，'.join(parts)}"
        if diff_lines:
            content += "<br>" + "<br>".join(diff_lines)

        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": PRODUCT_DOCTYPE,
            "reference_name": product.name,
            "content": content
        }).insert(ignore_permissions=True)

        logger.warning(f"成功處理 {artno} ({product.name})")
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
            count1 = 0
            for artno, data in products.items():
                create_or_update_product(data)
                count1 += 1
                if count1 % 500 == 0:
                    sleep(0.5)

            dest = os.path.join(PROCEED_DIR, PRODUCT_FILE)
            shutil.move(file_path, dest)
            logger.info(f"匯入完成，檔案移至: {dest}")

        logger.info("=== 匯入結束 ===")


# ============================ 手動驗證 Product 與 CSV 差異 ============================
def verify_product_csv_vs_db():
    """
    僅供手動檢查：比對 CSV 與資料庫的 article_number 差異
    """
    logger.info("=== 開始手動驗證 Product 與 CSV article_number 差異 ===")

    file_path = os.path.join(PROCEED_DIR, PRODUCT_FILE)
    if not os.path.isfile(file_path):
        logger.error(f"驗證失敗：找不到檔案 {file_path}")
        frappe.msgprint("找不到 xpin_products.txt 檔案！", alert=True)
        return

    csv_articles = set()
    try:
        with open(file_path, 'r', encoding='cp1252', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                artno = (row.get("ARTNO", "") or "").strip()
                if artno:
                    csv_articles.add(artno)
    except Exception as e:
        logger.error(f"讀取 CSV 失敗: {e}")
        frappe.msgprint(f"讀取 CSV 時發生錯誤: {e}", alert=True)
        return

    # 取得資料庫所有 article_number
    db_articles = set()
    try:
        db_products = frappe.get_all(
            PRODUCT_DOCTYPE,
            fields=["article_number"],
            filters={"article_number": ["!=", ""]}
        )
        for p in db_products:
            if p.article_number:
                db_articles.add(str(p.article_number).strip())
    except Exception as e:
        logger.error(f"查詢資料庫失敗: {e}")
        frappe.msgprint(f"查詢資料庫失敗: {e}", alert=True)
        return

    # 計算差異
    only_in_csv = sorted(csv_articles - db_articles)
    only_in_db = sorted(db_articles - csv_articles)

    total_csv = len(csv_articles)
    total_db = len(db_articles)

    result_msg = f"""
    <b>驗證完成！</b><br>
    CSV 檔案總筆數：{total_csv} 筆<br>
    資料庫 Product 總筆數：{total_db} 筆<br><br>
    """

    if only_in_csv:
        result_msg += f"<b style='color:red'>CSV 有，但資料庫沒有的（建議新增）：</b> {len(only_in_csv)} 筆<br>"
        result_msg += "<br>".join([f"• {art}" for art in only_in_csv[:100]])
        if len(only_in_csv) > 100:
            result_msg += f"<br>... 還有 {len(only_in_csv)-100} 筆"
        result_msg += "<br><br>"

    if only_in_db:
        result_msg += f"<b style='color:orange'>資料庫有，但 CSV 沒有的（可能已停售）：</b> {len(only_in_db)} 筆<br>"
        result_msg += "<br>".join([f"• {art}" for art in only_in_db[:100]])
        if len(only_in_db) > 100:
            result_msg += f"<br>... 還有 {len(only_in_db)-100} 筆"
        result_msg += "<br><br>"

    if not only_in_csv and not only_in_db:
        result_msg += "<b style='color:green'>✅ CSV 與資料庫的 article_number 完全一致！</b>"

    logger.info(result_msg.replace("<br>", " | ").replace("<b>", "").replace("</b>", ""))
    
    # 在前端顯示結果
    frappe.msgprint(result_msg, title="Product CSV 與資料庫比對結果", indicator="blue" if not only_in_csv and not only_in_db else "orange")