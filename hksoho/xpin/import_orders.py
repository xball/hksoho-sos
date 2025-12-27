import time
import frappe
import pandas as pd
from frappe.utils import getdate, flt, cint, now_datetime
from frappe import _

# 請修改為您的 Excel 檔案路徑
EXCEL_FILE_PATH = "/home/frappe/frappe-bench/temp/order_1.xlsx"  # 請上傳到 private/files 或調整路徑

DOCTYPE = "xpin_orders"
BATCH_SIZE = 100  # 每 100 筆 commit 一次，避免記憶體爆掉

# Link 欄位（需驗證是否存在）
LINK_FIELDS = {
    "agentid": "Partner",
    "buyerid": "Partner",
    "supplierid": "Partner",
    "custid": "Partner",
    "paytermcode": "Payment Term",
    "forwarderid": "Partner"  # 若有 forwarder
}

def import_xpin_orders():
    if not frappe.utils.os.path.exists(EXCEL_FILE_PATH):
        frappe.throw(_("檔案不存在：{}").format(EXCEL_FILE_PATH))

    print(f"開始匯入 {EXCEL_FILE_PATH} ...")

    # 使用 pandas 讀取（效率高）
    df = pd.read_excel(EXCEL_FILE_PATH, dtype=str)  # 先全讀成字串，避免自動轉型問題
    df = df.fillna("")  # NULL 轉空字串

    total = len(df)
    imported = 0
    skipped = 0

    for idx, row in df.iterrows():
        try:
            doc_data = {"doctype": DOCTYPE}

            # 逐欄位對應（直接用 header 名稱）
            for field in frappe.get_meta(DOCTYPE).fields:
                fieldname = field.fieldname
                if fieldname in row:
                    val = row[fieldname].strip() if row[fieldname] else None

                    # 特殊處理
                    if field.fieldtype == "Date" and val:
                        if val == "NULL" or val == "0000-00-00":
                            val = None
                        else:
                            val = getdate(val)
                    elif field.fieldtype in ["Float", "Currency"]:
                        val = flt(val) if val else 0.0
                    elif field.fieldtype in ["Int"]:
                        val = cint(val) if val and val.isdigit() else 0
                    elif field.fieldtype == "Link" and val:
                        doctype_link = LINK_FIELDS.get(fieldname, field.options)
                        if frappe.db.exists(doctype_link, val):
                            val = val
                        else:
                            print(f"第 {idx+2} 筆 Link 不存在：{fieldname} = {val}")
                            val = None
                    elif val == "NULL":
                        val = None

                    doc_data[fieldname] = val

            # 主鍵檢查（ordernr）
            ordernr = doc_data.get("ordernr")
            if not ordernr:
                skipped += 1
                continue

            if frappe.db.exists(DOCTYPE, ordernr):
                skipped += 1
                continue

            # 建立文件
            doc = frappe.get_doc(doc_data)
            doc.insert(ignore_permissions=True, ignore_links=False, ignore_mandatory=False)
            imported += 1

            if imported % BATCH_SIZE == 0:
                frappe.db.commit()
                print(f"已匯入 {imported} 筆，提交中...")
                time.sleep(5)

        except Exception as e:
            print(f"第 {idx+2} 筆匯入失敗（ordernr: {ordernr or '未知'}）：{str(e)}")
            skipped += 1
            continue

    frappe.db.commit()
    print(f"匯入完成！成功：{imported} 筆，跳過/錯誤：{skipped} 筆")

# 在 Bench Console 執行
# bench --site your_site_name execute your_app.import_script.import_xpin_orders