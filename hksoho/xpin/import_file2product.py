#!/usr/bin/env python
import os
import time
import click
import pandas as pd
import frappe
from frappe.utils import getdate

# === 需要依你的環境修改 ===
SITE_NAME = "sos.byrydens.com"  # 你的 site name
EXCEL_PATH = "/home/frappe/frappe-bench/temp/pd-list-1.xlsx"
OLD_BASE = "/home/frappe/frappe-bench/temp/prodfile"  # 舊系統檔案根目錄
# 下面用 private/files，你也可換 public/files
FRAPPE_FILES_PATH = f"/home/frappe/frappe-bench/sites/{SITE_NAME}/private/files"
FILE_URL_PREFIX = "/private/files"  # 若用 public 就改成 /files

FILE_TYPE_MAP = {
    "Label": "Label",
    "Drawing": "Drawing",
    "Image": "Image",
    # TODO: 其他舊系統 type 對應
}

def map_file_type(old_type: str) -> str:
    old_type = (old_type or "").strip()
    return FILE_TYPE_MAP.get(old_type, "Other")

def upsert_product_attachment(article_name, file_doc, uploaded, uploaded_by, file_type_old):
    product = frappe.get_value("Product", {"name": article_name}, "name")
    if not product:
        print(f"[SKIP] Product not found: {article_name}")
        return

    file_url = file_doc.file_url
    base_desc = os.path.splitext(file_doc.file_name)[0]

    # description：檔名 + Uploadedby 註記
    description = base_desc
    if uploaded_by:
        description += f"\nUploadedby: {uploaded_by}"

    pa_name = frappe.get_value(
        "Product Attachment",
        {"attachment_file": file_url},
        "name"
    )

    file_type = (file_type_old)

    if pa_name:
        pa = frappe.get_doc("Product Attachment", pa_name)
        pa.active = 1
        pa.description = description
    else:
        pa = frappe.get_doc({
            "doctype": "Product Attachment",
            "attachment_name": base_desc,
            "attachment_file": file_url,
            "file_type": file_type,
            "description": description,
            "active": 1,
        })
        if uploaded:
            try:
                pa.upload_date = getdate(uploaded)
            except Exception:
                pass
        # 不設定 uploaded_by，全部文字寫在 description

    # 檢查 / 新增 product_link
    exists = any(row.product == product for row in pa.product_link)
    if not exists:
        pa.append("product_link", {"product": product})

    pa.save(ignore_permissions=True)
    print(f"[OK] Product Attachment for file {file_doc.file_name} linked to {article_name}")

# @click.command()
# @click.option("--site", default=SITE_NAME, help="Frappe site name")
# def main(site):
#     frappe.init(site=site)
#     frappe.connect()
#     frappe.flags.in_migrate = True
def importing():
    site = SITE_NAME
    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name="Sheet3")
        print(f"=== 開始在 site '{site}' 匯入產品檔案資料 ===")
        print(f"讀取 Excel 檔案：{EXCEL_PATH}，共 {len(df)} 筆資料")
        count = 0
        for _, row in df.iterrows():
            article_name = str(row["article_name"]).strip()
            filename = str(row["filename"]).strip()
            folder = str(row["folder"]).strip()
            uid = str(row["UID"]).strip()
            uploaded = row.get("Uploaded")
            uploaded_by = str(row.get("UploadedBy") or "").strip()
            file_type_old = str(row.get("file-type") or "").strip()

            old_path = os.path.join(OLD_BASE, folder, uid)
            new_path = os.path.join(FRAPPE_FILES_PATH, filename)

            if not os.path.exists(old_path) and not os.path.exists(new_path):
                print(f"[MISS] File not found: {old_path}")
                continue

            # 如果新路徑還沒有檔案，就從舊路徑搬過來並改名
            if not os.path.exists(new_path) and os.path.exists(old_path):
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                os.rename(old_path, new_path)
                print(f"[MOVE] {old_path} -> {new_path}")
            else:
                print(f"[SKIP MOVE] Already at {new_path}")

            # 建 / 找 File
            file_url = f"{FILE_URL_PREFIX}/{filename}"
            file_name = filename

            file_name_in_db = frappe.get_value("File", {"file_url": file_url}, "name")
            if file_name_in_db:
                file_doc = frappe.get_doc("File", file_name_in_db)
            else:
                file_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": file_name,
                    "file_url": file_url,
                    "is_private": 1 if FILE_URL_PREFIX.startswith("/private") else 0,
                }).insert(ignore_permissions=True)
                print(f"[NEW FILE] {file_url}")

            # 建 / 更新 Product Attachment + child table
            upsert_product_attachment(
                article_name=article_name,
                file_doc=file_doc,
                uploaded=uploaded,
                uploaded_by=uploaded_by,
                file_type_old=file_type_old,
            )
            count += 1
            if count % 100 == 0:
                print(f"  已處理 {count} 筆資料...")
                # frappe.db.commit()
                time.sleep(3)


        frappe.db.commit()
        print("=== DONE ===")
    finally:
        frappe.destroy()

# if __name__ == "__main__":
#     main()
