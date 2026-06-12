import time
import frappe
import os
import pandas as pd

def update_xpin_po_items_description_from_xlsx(
    file_path="/home/frappe/frappe-bench/temp/update_po_item_fin.xlsx",
    commit_every=100
):
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return

    df = pd.read_excel(file_path)

    required_cols = {"PO", "Line", "LineDesc"}
    if not required_cols.issubset(set(df.columns)):
        print(f"[ERROR] Excel 缺少必要欄位: {required_cols}")
        return

    updated = 0
    not_found = []
    print(f"xls file -> {len(df)}")
    
    for idx, row in df.iterrows():
        po_no = str(row["PO"]).strip() if not pd.isna(row["PO"]) else None
        line_no = int(row["Line"]) if not pd.isna(row["Line"]) else None
        line_desc = "" if pd.isna(row["LineDesc"]) else str(row["LineDesc"]).strip()

        if not po_no or line_no is None:
            continue

        # 找到 child row 的 name
        child_name = frappe.db.get_value(
            "xpin_po_items",
            {"po_number": po_no, "line": line_no},
            "name"
        )

        if not child_name:
            not_found.append(f"Row {idx}: 找不到 xpin_po_items (PO={po_no}, Line={line_no})")
            continue

        # 讀舊值（可選，用嚟避免重複 update）
        old_desc = frappe.db.get_value("xpin_po_items", child_name, "description") or ""

        if old_desc.strip() != line_desc:
            # 直接更新 DB（不走 validate hooks）
            frappe.db.set_value(
                "xpin_po_items",
                child_name,
                "description",
                line_desc
            )
            updated += 1

        if commit_every and updated and updated % commit_every == 0:
            frappe.db.commit()
            time.sleep(0.5)
            print(f"已更新 {updated} 筆，執行 commit...")

    frappe.db.commit()

    print("========== 更新結果 ==========")
    print(f"更新完成：共更新 {updated} 筆 xpin_po_items.description。")
    print(f"找不到對應資料筆數：{len(not_found)}。")

    if not_found:
        print("\n前 50 筆找不到對應資料：")
        for line in not_found[:50]:
            print(line)

    print("=========== 完成 ===========")
