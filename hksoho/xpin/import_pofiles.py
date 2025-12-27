import os
import shutil
import time
import pandas as pd
import frappe
from frappe.utils import getdate

# === 依實際環境修改這幾個 ===
EXCEL_PATH = "/home/frappe/frappe-bench/temp/po_files-1.xlsx"
OLD_BASE = "/home/frappe/frappe-bench/sites/sos.byrydens.com/private/files/xpin/org"  # 舊系統根目錄，例如 /mnt/old
TARGET_SUBDIR = "private/files/xpin/po"  # 相對於 sites/{sitename}
DOCTYPE = "xpin_po_files"


def migrate_po_files():
    print("=== Start PO files migration ===")

    # 取得目前 site 的實體路徑
    site_path = frappe.get_site_path()
    frappe_files_path = os.path.join(site_path, "private/files/xpin/po")
    file_url_prefix = "/private/files/xpin/po"

    df = pd.read_excel(EXCEL_PATH, sheet_name="Sheet2")
    count = 0
    for _, row in df.iterrows():
        row_id = str(row["id"]).strip()
        filename = str(row["filename"]).strip()
        folder = str(row["folder"]).strip()
        idfilename_raw = row.get("Idfilename")
        uploaded = row.get("uploaded")
        uploadby = str(row.get("uploadby") or "").strip()
        file_type = str(row.get("file_type") or "").strip()
        doc_id = str(row.get("doc_id") or "").strip()
        po_number = str(row.get("po_number") or "").strip()

        # 1) 檢查 Idfilename
        if not idfilename_raw or (isinstance(idfilename_raw, float) and pd.isna(idfilename_raw)):
            print(f"[SKIP] Empty Idfilename, id={row_id}, filename={filename}")
            continue

        idfilename = str(idfilename_raw).strip()

        old_path = os.path.join(OLD_BASE, folder, idfilename)
        new_path = os.path.join(frappe_files_path, filename)

        # 2) 檔案存在性檢查
        if not os.path.exists(old_path) and not os.path.exists(new_path):
            print(f"[MISS] UID file not found: {old_path} (and new_path not found)")
            continue

        # 3) 搬檔 + 改名
        if not os.path.exists(new_path) and os.path.exists(old_path):
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(old_path, new_path)  # 會 copy + remove，支援跨磁碟
            print(f"[MOVE] {old_path} -> {new_path}")
        else:
            print(f"[SKIP MOVE] Already at {new_path}")


        # 4) 建 / 找 File
        file_url = f"{file_url_prefix}/{filename}"
        file_url = f"/private/files/xpin/po/{filename}"
        file_name = filename

        file_name_in_db = frappe.get_value("File", {"file_url": file_url}, "name")
        if file_name_in_db:
            file_doc = frappe.get_doc("File", file_name_in_db)
        else:
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": file_name,
                "file_url": file_url,
                "is_private": 1,
            }).insert(ignore_permissions=True)
            print(f"[NEW FILE] {file_url}")

        # 5) 建 / 更新 xpin_po_files
        doc_name = frappe.get_value(DOCTYPE, {"id": row_id}, "name")
        if doc_name:
            doc = frappe.get_doc(DOCTYPE, doc_name)
        else:
            doc = frappe.get_doc({"doctype": DOCTYPE, "id": row_id})

        doc.filename = filename
        doc.filelink = file_url  # Attach 欄位可以直接塞 URL

        if uploaded:
            try:
                doc.uploaded = getdate(uploaded)
            except Exception:
                pass

        # 建議把 DocType 的這兩欄改成 Data/Select，比較合理
        doc.uploadby = uploadby
        doc.file_type = file_type

        doc.doc_id = doc_id
        doc.po_number = po_number

        doc.save(ignore_permissions=True)
        print(f"[OK] {DOCTYPE} id={row_id}, file={filename}")
        count += 1
                    # 每 BATCH_SIZE 筆提交一次
        if count % 100 == 0:
            print(f"  已成功匯入 {count} 筆，提交資料庫...")
            frappe.db.commit()
            time.sleep(3)

    frappe.db.commit()
    print("=== PO files migration DONE ===")
