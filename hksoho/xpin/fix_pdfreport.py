import os
import time
import frappe

# 設定
subfolder = "xpin/pdf"                     # 子資料夾名稱
root_private_dir = frappe.get_site_path("private", "files")
pdf_dir = frappe.get_site_path("private", "files", "xpin", "pdf")

SLEEP_EVERY = 100          # 每處理 100 筆 commit 一次
SLEEP_SECONDS = 0.5        # 休息 0.5 秒

print("開始修正斷鏈的 File 記錄（根目錄檔案已刪除，但 file_url 仍指向舊路徑）")
print("子資料夾路徑:", pdf_dir)

# 統計
updated = 0
skipped_no_new_file = 0
already_correct = 0
total_checked = 0
processed = 0  # 用來計算已處理筆數

# 找出所有 file_url 指向根目錄、且 attached_to_doctype 是 xpin_po 的 File 記錄
file_list = frappe.db.get_list(
    "File",
    filters={
        "file_url": ["like", "/private/files/%.pdf"],
        "attached_to_doctype": "xpin_po",
        "is_private": 1
    },
    fields=["name", "file_url", "file_name", "attached_to_name"]
)

print(f"總共找到 {len(file_list)} 筆符合條件的 File 記錄，開始處理...")

for f in file_list:
    processed += 1
    total_checked += 1
    
    old_url = f.file_url
    filename = f.file_name or os.path.basename(old_url)
    new_url = f"/private/files/{subfolder}/{filename}"
    new_file_path = os.path.join(pdf_dir, filename)
    old_file_path = os.path.join(root_private_dir, filename)
    
    # 如果根目錄舊檔案還存在，視為已經正確或不需處理，跳過
    if os.path.exists(old_file_path):
        already_correct += 1
        continue
    
    # 如果新位置的檔案不存在，無法修正，記錄跳過
    if not os.path.exists(new_file_path):
        print(f"警告：新檔案不存在，無法修正斷鏈 File: {old_url} (xpin_po: {f.attached_to_name})")
        skipped_no_new_file += 1
        continue
    
    # 執行更新 File 記錄
    try:
        file_doc = frappe.get_doc("File", f.name)
        file_doc.file_url = new_url
        file_doc.is_private = 1
        file_doc.folder = "Home/Attachments"  # 可自行調整資料夾
        file_doc.save(ignore_permissions=True)
        
        updated += 1
        print(f"[{processed}/{len(file_list)}] 已修正斷鏈 File: {old_url} → {new_url} (xpin_po: {f.attached_to_name})")
        
    except Exception as e:
        print(f"更新失敗: {f.name}, 錯誤: {str(e)}")
        frappe.log_error(f"修正斷鏈 File 失敗: {f.name}, {str(e)}", "File Broken Link Fix Error")

    # 每處理 100 筆就 commit 並休息一下
    if processed % SLEEP_EVERY == 0:
        frappe.db.commit()
        print(f"已處理 {processed} 筆，執行 commit 並休息 {SLEEP_SECONDS} 秒...")
        time.sleep(SLEEP_SECONDS)

# 最後一次 commit
frappe.db.commit()

# 輸出統計結果
print("\n=== 斷鏈修正完成 ===")
print(f"總檢查 File 記錄數: {total_checked}")
print(f"成功修正斷鏈數量: {updated}")
print(f"跳過 - 新檔案不存在: {skipped_no_new_file}")
print(f"跳過 - 舊檔案仍存在（視為已正確）: {already_correct}")
print(f"總符合條件 File 筆數: {len(file_list)}")