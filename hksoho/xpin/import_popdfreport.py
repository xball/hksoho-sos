import os
import time
import frappe
from frappe.utils import now
from datetime import date

# 設定參數
SLEEP_EVERY = 100          # 每處理 100 筆 commit 一次
SLEEP_SECONDS = 0.5        # 休息 0.5 秒，避免資料庫負載過高
TARGET_DATE = date(2025, 12, 29)   # 只刪除這一天在根目錄的重複檔

# 路徑設定
pdf_dir = frappe.get_site_path("private", "files", "xpin", "pdf")
root_private_dir = frappe.get_site_path("private", "files")

print("PDF 資料夾路徑:", pdf_dir)
print("根目錄 private/files 路徑:", root_private_dir)

# 檢查資料夾是否存在
if not os.path.exists(pdf_dir):
    raise Exception(f"資料夾不存在: {pdf_dir}")

# 取得所有 PDF 檔案（排序方便觀察）
files = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")])
print("找到 PDF 檔案數量:", len(files))

# 統計變數
created = updated = skipped = processed = 0
deleted_root = skipped_root_date = skipped_root_db_ref = skipped_root_not_exist = 0

for filename in files:
    po_number = os.path.splitext(filename)[0].strip()  # 去除可能的空白
    file_url = f"/private/files/xpin/pdf/{filename}"   # 新檔案的 URL（子目錄）
    new_file_path = os.path.join(pdf_dir, filename)    # 新檔案實際路徑
    
    # 檢查對應的 xpin_po 是否存在
    if not frappe.db.exists("xpin_po", po_number):
        skipped += 1
        continue

    # ===== 1) 建立或更新 File 記錄 =====
    file_docname = frappe.db.get_value("File", {"file_url": file_url}, "name")
    
    try:
        if not file_docname:
            # 建立新的 File 記錄
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": filename,
                "file_url": file_url,
                "is_private": 1,
                "attached_to_doctype": "xpin_po",
                "attached_to_name": po_number,
                "attached_to_field": "pdf_report",
                "folder": "Home/Attachments"  # 可自行調整資料夾
            })
            file_doc.insert(ignore_permissions=True)
            created += 1
            frappe.log_error(f"Created File: {file_url} for xpin_po {po_number}", "PDF Migration")
        else:
            # 更新現有的 File 記錄
            file_doc = frappe.get_doc("File", file_docname)
            need_save = False
            
            if file_doc.attached_to_doctype != "xpin_po" or \
               file_doc.attached_to_name != po_number or \
               file_doc.attached_to_field != "pdf_report":
                file_doc.attached_to_doctype = "xpin_po"
                file_doc.attached_to_name = po_number
                file_doc.attached_to_field = "pdf_report"
                need_save = True
            
            if file_doc.is_private != 1:
                file_doc.is_private = 1
                need_save = True
                
            if need_save:
                file_doc.save(ignore_permissions=True)
                updated += 1
                
        # 更新 xpin_po 的 pdf_report 欄位
        current_pdf = frappe.db.get_value("xpin_po", po_number, "pdf_report")
        if current_pdf != file_url:
            frappe.db.set_value("xpin_po", po_number, "pdf_report", file_url)
            
    except Exception as e:
        frappe.log_error(f"處理 File 時發生錯誤: {filename}, 錯誤: {str(e)}", "PDF Migration Error")

    # ===== 2) 清理根目錄重複檔 =====
    root_path = os.path.join(root_private_dir, filename)
    old_url = f"/private/files/{filename}"
    
    if os.path.exists(root_path):
        # 取得檔案修改時間（視為建立時間）
        fdate = date.fromtimestamp(os.path.getmtime(root_path))
        
        if fdate != TARGET_DATE:
            skipped_root_date += 1
        else:
            # 檢查是否仍有其他 File 記錄引用舊 URL
            if frappe.db.exists("File", {"file_url": old_url}):
                skipped_root_db_ref += 1
            else:
                # 額外安全檢查：確認子目錄的新檔確實存在
                if os.path.exists(new_file_path):
                    try:
                        os.remove(root_path)
                        deleted_root += 1
                        frappe.log_error(f"Deleted root duplicate: {root_path}", "PDF Migration Cleanup")
                    except Exception as e:
                        frappe.log_error(f"刪除失敗: {root_path}, 錯誤: {str(e)}", "PDF Migration Delete Error")
                else:
                    frappe.log_error(f"新檔不存在，跳過刪除舊檔: {root_path}", "PDF Migration Safety")
    else:
        skipped_root_not_exist += 1

    processed += 1
    
    # 每處理一定數量 commit 並休息
    if processed % SLEEP_EVERY == 0:
        frappe.db.commit()
        print(
            f"已處理 {processed}/{len(files)} | "
            f"新建 File {created}, 更新 File {updated}, 刪除根目錄檔 {deleted_root} ... "
            f"休息 {SLEEP_SECONDS} 秒"
        )
        time.sleep(SLEEP_SECONDS)

# 最後 commit
frappe.db.commit()

# 輸出最終統計
print("=== 執行完成 ===")
print(f"總處理檔案: {processed}")
print(f"新建 File 記錄: {created}")
print(f"更新 File 記錄: {updated}")
print(f"跳過（無對應 xpin_po）: {skipped}")
print(f"刪除根目錄重複檔: {deleted_root}")
print(f"跳過刪除 - 日期不符: {skipped_root_date}")
print(f"跳過刪除 - 仍有 DB 引用: {skipped_root_db_ref}")
print(f"跳過刪除 - 根目錄檔案不存在: {skipped_root_not_exist}")