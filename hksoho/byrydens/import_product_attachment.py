# -*- coding: utf-8 -*-
# File: apps/hksoho/hksoho/byrydens/import_product_attachment.py

import frappe
import pandas as pd
import os
import re
import time
import json
from frappe.utils import today, now
frappe.flags.in_migrate = True
# 斷點續傳記錄檔
RESUME_FILE = "/home/frappe/frappe-bench/temp/product_attachment_resume.json"

def get_last_processed_index():
    if os.path.exists(RESUME_FILE):
        try:
            with open(RESUME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_index", -1)
        except:
            return -1
    return -1

def save_progress(index, total):
    with open(RESUME_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_index": index, "total": total, "saved_at": now()}, f, indent=2)

def run_test(excel_path=None, local_folder=None, batch_size=200):
    frappe.log("================================================")
    frappe.log("Product Attachment 終極斷點續傳版（已修復所有 typo）")
    frappe.log("================================================")

    if not excel_path:
        excel_path = "/home/frappe/frappe-bench/temp/product_data.xlsx"
    if not local_folder:
        local_folder = "/home/frappe/frappe-bench/temp"

    df = pd.read_excel(excel_path)
    total = len(df)
    last_index = get_last_processed_index()
    start_from = last_index + 1 if last_index >= 0 else 0

    success = max(last_index + 1, 0)
    frappe.log(f"總共 {total} 筆，上次處理到第 {last_index+1} 筆，本次從第 {start_from+1} 筆開始")

    for start in range(start_from, total, batch_size):
        end = min(start + batch_size, total)
        batch_df = df.iloc[start:end]
        frappe.log(f"\n正在處理第 {start+1} ~ {end} 筆（共 {total} 筆）...")

        frappe.clear_cache()
        frappe.db.commit()

        for idx in range(start, end):
            row = df.iloc[idx]
            try:
                raw_filename = str(row["Filename"]) if pd.notna(row["Filename"]) else ""
                if not raw_filename or raw_filename == "nan":
                    continue

                clean_filename = raw_filename.replace("\xa0", " ").strip()

                # 檢查是否已存在（雙重保險）
                if frappe.db.exists("Product Attachment", {"attachment_name": clean_filename}):
                    success += 1
                    save_progress(idx, total)
                    continue

                file_type = str(row["Type"]).strip()
                upload_date = pd.to_datetime(row["Uploaded Date"]).date()
                uploaded_by_name = str(row["Uploaded By"]).strip()
                article_numbers = str(row["Article Numbers"]).strip() if pd.notna(row["Article Numbers"]) else ""
                local_path = str(row["Local Path"]).strip().replace("\\", "/")

                full_file_path = os.path.join(local_folder, local_path)
                
                if not os.path.exists(full_file_path):
                    frappe.log(f"警告：檔案不存在，跳過此筆 → {full_file_path}")
                    save_progress(idx, total)  # 仍記錄進度，避免重複嘗試
                    continue  # 直接跳過，不炸掉

                user = frappe.db.get_value("User", {"full_name": ["like", f"%{uploaded_by_name}%"]}, "name") \
                    or frappe.db.get_value("User", {"name": uploaded_by_name}, "name") \
                    or "Administrator"

                doc = frappe.new_doc("Product Attachment")
                doc.attachment_name = clean_filename
                doc.file_type = file_type
                doc.description = f"舊系統匯入 - {uploaded_by_name} 於 {upload_date} 上傳"
                doc.upload_date = upload_date
                doc.uploaded_by = user
                doc.active = 1

                # 自動抓版本
                ver = re.search(r'v(\d+\.?\d*)', raw_filename, re.I)
                if ver:
                    doc.version = ver.group(1)

                # 上傳 Private 檔案（關鍵修正！）
                with open(full_file_path, "rb") as f:
                    filedoc = frappe.get_doc({
                        "doctype": "File",
                        "file_name": os.path.basename(full_file_path),   # 修正 typo
                        "folder": "Home/Attachments",
                        "is_private": 1,
                        "content": f.read()
                    }).insert(ignore_permissions=True)

                doc.attachment_file = filedoc.file_url

                # 子表格

                if article_numbers and article_numbers.lower() != "nan":
                    items = [x.strip() for x in article_numbers.split(",") if x.strip()]
                    valid_items = []
                    for itm in items:
                        if frappe.db.exists("Item", {"name": itm}):
                            valid_items.append(itm)
                        else:
                            frappe.log(f"品號不存在，跳過連結：{itm}（附件仍會匯入）")
                    
                    # 只加存在的品號
                    for itm in valid_items:
                        doc.append("product_link", {
                            "product": itm,
                            "item_code": itm
                        })
                    
                    # 如果全部都不存在，至少留個備註
                    if not valid_items:
                        doc.description += f" | 注意：品號 {items} 尚未建立，連結已略過"




                doc.insert(ignore_permissions=True)
                success += 1
                save_progress(idx, total)   # 每成功一筆就存進度

                if success % 20 == 0:
                    frappe.log(f"已成功匯入 {success} 筆（進度 {idx+1}/{total}）")

            except Exception as e:
                err = f"第 {idx+2} 列失敗 → {clean_filename} | 錯誤：{str(e)}"
                short_err = f"第 {idx+2} 列失敗 → {clean_filename[:50]} | 檔案不存在或錯誤"
                frappe.log_error(err, short_err[:140])  # 強制截斷在 140 字內

        # 批次結束清理
        frappe.db.commit()
        frappe.clear_cache()
        if hasattr(frappe.local, "file_data"):
            frappe.local.file_data = {}
        frappe.log(f"第 {end} 筆批次完成，已 commit + 徹底清理記憶體")

        if end < total:
            time.sleep(3)

    # 全部完成 → 刪除續傳檔
    if os.path.exists(RESUME_FILE):
        os.remove(RESUME_FILE)
        frappe.log("全部匯入完成，斷點記錄檔已清除！")

    result = f"""
    匯入完畢！
    總筆數：{total}
    成功：{success} 筆
    完成時間：{now()}
    """
    frappe.msgprint(result, title="大功告成！", indicator="green")
    print(result)


if __name__ == "__main__":
    run_test(batch_size=10)