import os
import time
import frappe
import pandas as pd
from frappe.utils import getdate, flt, cint

# ===== 請修改以下設定 =====
EXCEL_FILE_PATH = "/home/frappe/frappe-bench/temp/orderitem-1.xlsx"  # 改成您的實際檔案路徑
# 如果您上傳到 Frappe 的 private/files 資料夾，可用以下方式：
# EXCEL_FILE_PATH = frappe.get_site_path("private", "files", "orderitem-1.xlsx")

DOCTYPE = "xpin_order_items"
BATCH_SIZE = 100  # 每 100 筆提交一次資料庫，避免記憶體過載

# Link 欄位處理（目前只有 qcresult 是 Link）
LINK_FIELDS = {
    "qcresult": "xpin_inspection_results"
}

def import_order_items_from_excel():
    if not os.path.exists(EXCEL_FILE_PATH):
        frappe.throw(f"檔案不存在：{EXCEL_FILE_PATH}")

    print(f"開始匯入 {EXCEL_FILE_PATH} 到 {DOCTYPE}...")

    # 使用 pandas 讀取 Excel（效能好，處理大量資料穩定）
    df = pd.read_excel(EXCEL_FILE_PATH, sheet_name="order_items_fixed", dtype=str)
    df = df.fillna("")  # 將 NaN 轉為空字串

    total = len(df)
    print(f"總共發現 {total} 筆訂單項目資料")

    imported = 0
    skipped = 0

    for idx, row in df.iterrows():
        try:
            doc_data = {"doctype": DOCTYPE}

            # 逐欄位對應（使用 Excel 標題直接對應 DocType fieldname）
            for field in frappe.get_meta(DOCTYPE).get("fields"):
                fieldname = field.fieldname
                if fieldname in row:
                    val = row[fieldname].strip() if pd.notna(row[fieldname]) and row[fieldname] != "" else None

                    # 特殊欄位類型處理
                    if field.fieldtype == "Date" and val:
                        if val in ["NULL", "0000-00-00", ""]:
                            doc_data[fieldname] = None
                        else:
                            try:
                                doc_data[fieldname] = getdate(val)
                            except:
                                print(f"第 {idx+2} 筆：日期格式錯誤 {fieldname} = {val}，設為 None")
                                doc_data[fieldname] = None

                    elif field.fieldtype in ["Float", "Currency"]:
                        doc_data[fieldname] = flt(val) if val else 0.0

                    elif field.fieldtype in ["Int"]:
                        doc_data[fieldname] = cint(val) if val and val.isdigit() else 0

                    elif field.fieldtype == "Link" and val:
                        link_doctype = LINK_FIELDS.get(fieldname, field.options)
                        if frappe.db.exists(link_doctype, val):
                            doc_data[fieldname] = val
                        else:
                            print(f"第 {idx+2} 筆：Link 值不存在 {fieldname} = {val}，設為 None")
                            doc_data[fieldname] = None

                    elif field.fieldtype in ["Text", "Long Text"]:
                        doc_data[fieldname] = val if val else None

                    else:
                        doc_data[fieldname] = val if val not in ["NULL", ""] else None

            # 主鍵檢查：itemid 是唯一識別
            itemid = doc_data.get("itemid")
            if not itemid:
                print(f"第 {idx+2} 筆：缺少 itemid，跳過此筆")
                skipped += 1
                continue

            # 避免重複匯入
            if frappe.db.exists(DOCTYPE, itemid):
                skipped += 1
                continue

            # 建立文件
            doc = frappe.get_doc(doc_data)
            doc.insert(
                ignore_permissions=True,
                ignore_links=True,      # 若 qcresult 不存在不會中斷
                ignore_mandatory=True  # 允許部分必填欄位暫時為空
            )
            imported += 1

            # 每 BATCH_SIZE 筆提交一次
            if imported % BATCH_SIZE == 0:
                frappe.db.commit()
                print(f"  已成功匯入 {imported} 筆，提交資料庫...")
                time.sleep(3)

        except Exception as e:
            frappe.db.rollback()
            print(f"第 {idx+2} 筆匯入失敗（itemid: {itemid or '未知'}）：{str(e)}")
            skipped += 1
            continue

    # 最後提交剩餘資料
    frappe.db.commit()
    print("\n=== 匯入完成 ===")
    print(f"成功匯入：{imported} 筆")
    print(f"跳過或失敗：{skipped} 筆")

# 執行方式（在 bench console）：
# bench --site sos.byrydens.com execute hksoho.xpin.import_xpin_order_items.import_order_items_from_excel

if __name__ == "__main__":
    import_order_items_from_excel()