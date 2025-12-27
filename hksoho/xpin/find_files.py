import time
import frappe
import os

def debug_print_file_by_filename(filename: str):
    files = frappe.get_all(
        "File",
        filters={"file_name": filename},
        fields=[
            "name",
            "file_name",
            "file_url",
            "is_private",
            "attached_to_doctype",
            "attached_to_name",
            "attached_to_field",
            "content_hash",
            "creation",
            "owner",
        ],
    )
    print(f"=== File records for filename = {filename} ===")
    for f in files:
        print("-" * 60)
        for k, v in f.items():
            print(f"{k}: {v}")
    print(f"Total: {len(files)}")


def clean_root_po_file_duplicates():
    """清理 2025-12-24 當天產生的「根目錄 File + 檔案」重複項。

    規則：
    - 以 xpin_po_files.filename 為主。
    - 找出同一 file_name 對應的 File 記錄。
    - 若同時存在：
        * file_url = /private/files/xpin/po/<filename>
        * file_url = /private/files/<filename>，且 creation 是 2025-12-24 當天
      則刪除根目錄那一筆 File 記錄 + 實體檔。
    """
    site_path = frappe.get_site_path()
    base_private = os.path.join(site_path, "private/files")
    target_dir = os.path.join(site_path, "private/files/xpin/po")

    # 先抓出所有 xpin_po_files 的 filename
    docs = frappe.get_all(
        "xpin_po_files",
        fields=["name", "filename"],
    )

    removed_docs = 0
    removed_files = 0
    skipped = 0

    for d in docs:
        filename = (d.get("filename") or "").strip()
        if not filename:
            skipped += 1
            continue

        # 確認 xpin/po 版本存在，沒有就不動
        po_path = os.path.join(target_dir, filename)
        if not os.path.exists(po_path):
            # xpin/po 本身就沒有檔案，先不要亂刪
            skipped += 1
            continue

        # 找出所有同 file_name 的 File 記錄
        files = frappe.get_all(
            "File",
            filters={"file_name": filename},
            fields=[
                "name",
                "file_url",
                "is_private",
                "attached_to_doctype",
                "attached_to_name",
                "creation",
            ],
        )

        if not files:
            skipped += 1
            continue
        count = 0
        # 判斷是否有「根目錄版本」且 creation 在 2025-12-24
        for f in files:
            if f.file_url == f"/private/files/{filename}":
                # 只清理 2025-12-24 當天建立的
                creation_date = str(f.creation)[:10]
                if creation_date not in ("2025-12-24", "2025-12-25"):
                    print(f"[SKIP] Root File {f.name} ({f.file_url}) creation {creation_date} not in 2025-12-24/25")                    
                    continue

                # 實體根目錄檔案路徑
                root_path = os.path.join(base_private, filename)

                # 先刪實體檔
                if os.path.exists(root_path):
                    os.remove(root_path)
                    removed_files += 1
                    print(f"[DEL FILE] {root_path}")
                else:
                    print(f"[MISS FILE] {root_path} not found (only delete DB record)")

                # 再刪 DB 記錄
                frappe.delete_doc("File", f.name, ignore_permissions=True, force=True)
                removed_docs += 1
                print(f"[DEL DOC] File {f.name} ({f.file_url}) for filename={filename}")
        removed_docs += 1    
        if removed_docs % 100 == 0:
            print(f"  已成功removed_docs{removed_docs} 筆，提交資料庫...")
            frappe.db.commit()
            time.sleep(2)

    frappe.db.commit()
    print("=== clean_root_po_file_duplicates DONE ===")
    print(f"Removed File docs: {removed_docs}, Removed physical files: {removed_files}, Skipped: {skipped}")
