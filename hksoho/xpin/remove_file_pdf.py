import os
import time
import frappe
from collections import defaultdict

# 設定
subfolder_path = "/private/files/xpin/pdf/"
pdf_dir = frappe.get_site_path("private", "files", "xpin", "pdf")

SLEEP_EVERY = 100
SLEEP_SECONDS = 0.5

print("開始清理 File 中 file_url 完全相同的重複記錄（同一子資料夾路徑）")

# 統計
deleted_duplicates = 0
groups_processed = 0
skipped_no_duplicate = 0

# Step 1: 找出所有指向 xpin/pdf 子資料夾的 File 記錄
file_list = frappe.db.get_list(
    "File",
    filters={"file_url": ["like", f"{subfolder_path}%.pdf"]},
    fields=["name", "file_url", "creation", "attached_to_name", "attached_to_doctype"],
)

# Step 2: 用 file_url 分組
url_groups = defaultdict(list)
for f in file_list:
    url_groups[f.file_url].append({
        "name": f.name,
        "creation": f.creation,
        "attached_to_name": f.attached_to_name,
        "attached_to_doctype": f.attached_to_doctype
    })

print(f"總共找到 {len(file_list)} 筆 File 記錄，屬於 {len(url_groups)} 個唯一 URL")

# Step 3: 處理每一組
processed = 0
for file_url, records in url_groups.items():
    processed += 1
    groups_processed += 1
    
    if len(records) <= 1:
        skipped_no_duplicate += 1
        continue
    
    filename = os.path.basename(file_url)
    print(f"\n發現重複 [{len(records)} 筆]：{file_url}")
    
    # 優先保留：被 xpin_po.pdf_report 實際引用的那一筆
    referenced_records = []
    for rec in records:
        if (rec["attached_to_doctype"] == "xpin_po" and 
            rec["attached_to_name"] and 
            frappe.db.get_value("xpin_po", rec["attached_to_name"], "pdf_report") == file_url):
            referenced_records.append(rec)
    
    if referenced_records:
        # 有被引用的，保留所有被引用的（通常只有一筆），刪除其餘
        keep_records = referenced_records
    else:
        # 都沒有被引用，保留 creation 最新的那一筆
        keep_records = [max(records, key=lambda x: x["creation"])]
    
    # 要刪除的記錄
    delete_records = [r for r in records if r not in keep_records]
    
    for rec in delete_records:
        try:
            frappe.delete_doc("File", rec["name"], ignore_permissions=True, force=True)
            deleted_duplicates += 1
            print(f"  已刪除孤兒重複記錄: {rec['name']} (creation: {rec['creation']})")
        except Exception as e:
            print(f"  刪除失敗 {rec['name']}: {str(e)}")
            frappe.log_error(f"刪除重複 File 失敗: {rec['name']}, URL: {file_url}", "File Duplicate Same URL Cleanup")
    
    # 每處理一定數量 commit 並休息
    if processed % SLEEP_EVERY == 0:
        frappe.db.commit()
        print(f"已處理 {processed}/{len(url_groups)} 個 URL 組別，執行 commit 並休息 {SLEEP_SECONDS} 秒...")
        time.sleep(SLEEP_SECONDS)

# 最後 commit
frappe.db.commit()

# 輸出統計
print("\n=== 同一 URL 重複記錄清理完成 ===")
print(f"總檢查 URL 組數: {len(url_groups)}")
print(f"成功刪除的重複記錄數量: {deleted_duplicates}")
print(f"無重複（只有一筆）: {skipped_no_duplicate}")
print(f"有重複的組數: {groups_processed - skipped_no_duplicate}")