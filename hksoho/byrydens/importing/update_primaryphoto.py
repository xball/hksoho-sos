import frappe
import os
import csv
import logging
import time
from datetime import datetime
from frappe.utils.file_manager import save_file
from PIL import Image                    # ← 新增：自動壓縮圖片用
import io                                # ← 新增：在記憶體中處理

# ====================== 路徑設定 ======================
INPUT_DIR = frappe.get_site_config().get("partner_import_input_dir", "/home/ftpuser/ftp")
IMAGE_INPUT_DIR = frappe.get_site_config().get("partner_import_image_dir", "/home/ftpuser/ftp/img")
LOG_FILE = frappe.get_site_config().get(
    "product_import_log_file",
    "/home/frappe/frappe-bench/sites/sos.byrydens.com/logs/product_missing_image.log"
)
PRODUCT_FILE = "xpin_products.txt"

# ====================== 重要設定 ======================
DRY_RUN = True                    # ← 先保持 True 測試，確認沒問題再改 False
SLEEP_SECONDS = 2.0               # ← 每筆休息 2 秒，避免系統過載
MAX_FILE_SIZE_MB = 8.0            # ← 自動壓縮上限（低於 10MB 安全值）

# ============================ 日誌設定 ============================
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    filename=LOG_FILE,
    filemode='a',
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP')

# ============================ 新增：自動壓縮圖片函數 ============================
def resize_and_compress_image(image_path, max_mb=8.0):
    """如果圖片太大，自動縮小尺寸 + 壓縮品質"""
    max_bytes = max_mb * 1024 * 1024
    original_size = os.path.getsize(image_path) / (1024 * 1024)

    with Image.open(image_path) as img:
        # 轉成 RGB（避免 PNG 透明問題）
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # 縮小尺寸（最長邊不超過 2000px）
        max_dimension = 2000
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # 壓縮品質
        output = io.BytesIO()
        quality = 85
        img.save(output, format='JPEG', quality=quality, optimize=True)
        resized_content = output.getvalue()

        # 如果還是太大，再降低品質
        while len(resized_content) > max_bytes and quality > 60:
            quality -= 5
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            resized_content = output.getvalue()

        new_size_mb = len(resized_content) / (1024 * 1024)
        logger.info(f"圖片壓縮完成：{original_size:.2f}MB → {new_size_mb:.2f}MB (品質 {quality}%)")
        return resized_content

# ============================ 工具函數（找圖） ============================
def find_real_image_file(image_field_value, artno):
    if not image_field_value:
        return None
    raw_name = str(image_field_value).strip().strip('"').strip("'")
    if not raw_name:
        return None

    direct_path = os.path.join(IMAGE_INPUT_DIR, raw_name)
    if os.path.isfile(direct_path):
        logger.info(f"直接命中圖片: {direct_path} (ARTNO: {artno})")
        return direct_path

    base_name = os.path.splitext(raw_name)[0]
    possible_names = set()
    for ext in IMAGE_EXTENSIONS:
        possible_names.add(base_name + ext)
        possible_names.add(base_name.lower() + ext)
        possible_names.add(base_name.upper() + ext)

    for name in possible_names:
        full_path = os.path.join(IMAGE_INPUT_DIR, name)
        if os.path.isfile(full_path):
            logger.info(f"智慧搜尋命中: {full_path} ← 來自 IMAGE 欄位: {raw_name} (ARTNO: {artno})")
            return full_path

    logger.warning(f"找不到圖片檔案: {raw_name} (ARTNO: {artno})")
    return None


# ============================ 上傳與更新主圖（已加入自動壓縮） ============================
def upload_and_set_primary_image(product_name, image_path, article_number):
    if DRY_RUN:
        logger.info(f"【DRY-RUN 模擬】ARTNO: {article_number} → {os.path.basename(image_path)}（會自動壓縮大圖）")
        return True

    try:
        with open(image_path, "rb") as f:
            content = f.read()

        # 自動壓縮大圖片
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            content = resize_and_compress_image(image_path, MAX_FILE_SIZE_MB)

        # 使用 Frappe 官方 save_file（最穩定）
        file_doc = save_file(
            fname=os.path.basename(image_path),
            content=content,
            dt="Product",
            dn=product_name,
            is_private=0
        )

        # 直接更新 primary_image
        frappe.db.set_value("Product", product_name, "primary_image", file_doc.file_url)
        frappe.db.commit()

        logger.info(f"✅ 成功補上主圖 → {file_doc.file_url} (ARTNO: {article_number})")
        return True

    except Exception as e:
        logger.error(f"❌ 上傳失敗 (ARTNO: {article_number}) | 錯誤: {str(e)}")
        return False


# ============================ 主函數 ============================
def update_missing_primary_images():
    logger.info("=== 開始執行【補齊缺少主圖 + 自動壓縮】任務 ===")
    logger.info(f"DRY_RUN: {'開啟（只模擬）' if DRY_RUN else '關閉（真正執行）'}")
    logger.info(f"每筆休息 {SLEEP_SECONDS} 秒 | 壓縮上限 {MAX_FILE_SIZE_MB} MB")

    # 讀取 TXT 建立圖片對照表
    file_path = os.path.join(INPUT_DIR, PRODUCT_FILE)
    if not os.path.isfile(file_path):
        logger.error(f"找不到 xpin_products.txt: {file_path}")
        return

    image_map = {}
    try:
        with open(file_path, 'r', encoding='cp1252', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                artno = (row.get("ARTNO", "") or "").strip()
                if not artno:
                    continue
                real_path = find_real_image_file(row.get("IMAGE", ""), artno)
                if real_path:
                    image_map[artno] = real_path
    except Exception as e:
        logger.error(f"讀取 TXT 失敗: {e}")
        return

    logger.info(f"TXT 中找到 {len(image_map)} 筆有圖片的商品")

    # 查詢缺少主圖的商品
    missing_products = frappe.db.get_all(
        "Product",
        filters={"primary_image": ["in", [None, ""]]},
        fields=["name", "article_number"]
    )

    logger.info(f"系統中共有 {len(missing_products)} 筆缺少主圖")

    updated_count = 0
    total = len(missing_products)
    for i, prod in enumerate(missing_products, 1):
        artno = prod.get("article_number")
        product_name = prod.get("name")

        if not artno or artno not in image_map:
            continue

        image_path = image_map[artno]
        if upload_and_set_primary_image(product_name, image_path, artno):
            updated_count += 1

        if i % 10 == 0:
            logger.info(f"進度: {i}/{total} 筆已處理，成功補圖 {updated_count} 張")

        time.sleep(SLEEP_SECONDS)

    logger.info(f"=== 任務完成！共成功補上 {updated_count} 張主圖 ===")


# ============================ 執行入口 ============================
if __name__ == "__main__":
    update_missing_primary_images()