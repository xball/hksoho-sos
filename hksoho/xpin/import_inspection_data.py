import os
import time
import csv
import frappe
from frappe.utils import getdate

# 資料夾路徑
IMPORT_FOLDER = "/home/frappe/frappe-bench/temp/splitted"

DOCTYPE = "xpin_inspection_data"

FIELD_MAPPING = [
    "id", "inspectionid", "itemid", "numinspection", "section", "linenumber",
    "sublevel1", "sublevel2", "description", "result", "errorcode",
    "cause_for_reinspection", "cause_for_remark", "notes", "value", "valueextra",
    "inserted", "insertby", "updated", "updateby"
]

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}

def id_exists(id_value):
    """檢查 id 是否已存在於資料庫"""
    if not id_value:
        return False
    return frappe.db.exists(DOCTYPE, id_value)

def import_single_file(file_path):
    delimiter = '\t' if file_path.endswith(('.tsv', '.csv')) else ','
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader)
        headers = [h.strip() for h in headers]

        count = 0
        batch_size = 500
        batch = []  # 暫存當前 500 筆

        for row in reader:
            if not row or len(row) < len(FIELD_MAPPING):
                continue

            doc_data = {}
            for i, field in enumerate(FIELD_MAPPING):
                value = row[i].strip() if i < len(row) else None
                if value in ("NULL", ""):
                    value = None

                if field == "id":
                    doc_data["id"] = value if value else frappe.generate_hash(length=10)
                elif field in ["numinspection", "linenumber", "sublevel1", "sublevel2"]:
                    doc_data[field] = int(value) if value and value.isdigit() else 0
                elif field in ["inserted", "updated"]:
                    doc_data[field] = getdate(value) if value else None
                else:
                    doc_data[field] = value

            batch.append(doc_data)
            count += 1

            # 每 500 筆處理一次
            if len(batch) == batch_size:
                first_id = batch[0].get("id")
                last_id = batch[-1].get("id")

                # 檢查第一筆與最後一筆是否都存在
                if first_id and last_id and id_exists(first_id) and id_exists(last_id):
                    print(f"  批次 {count - batch_size + 1} ~ {count} 已存在，跳過...")
                else:
                    print(f"  處理批次 {count - batch_size + 1} ~ {count}（第一筆 id: {first_id}, 最後一筆 id: {last_id}）")
                    for data in batch:
                        try:
                            doc = frappe.get_doc({
                                "doctype": DOCTYPE,
                                **data
                            })
                            doc.insert(ignore_permissions=True, ignore_mandatory=True)
                        except Exception as e:
                            print(f"  匯入失敗 (id: {data['id']}): {str(e)}")
                            continue

                batch = []  # 清空批次

                if count % 1000 == 0:
                    print(f"  已處理 {count} 筆資料...")

        # 處理最後不足 500 筆的批次
        if batch:
            first_id = batch[0].get("id")
            last_id = batch[-1].get("id")
            if first_id and last_id and id_exists(first_id) and id_exists(last_id):
                print(f"  最後批次 {count - len(batch) + 1} ~ {count} 已存在，跳過...")
            else:
                print(f"  處理最後批次 {count - len(batch) + 1} ~ {count}")
                for data in batch:
                    try:
                        doc = frappe.get_doc({
                            "doctype": DOCTYPE,
                            **data
                        })
                        doc.insert(ignore_permissions=True, ignore_mandatory=True)
                    except Exception as e:
                        print(f"  匯入失敗 (id: {data['id']}): {str(e)}")
                        continue

        print(f"  總共處理 {count} 筆資料（部分可能已跳過）")

# import_all_files() 保持不變
def import_all_files():
    files = sorted([f for f in os.listdir(IMPORT_FOLDER)
                    if os.path.isfile(os.path.join(IMPORT_FOLDER, f))
                    and os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS])

    total_files = len(files)
    print(f"發現 {total_files} 個檔案要匯入...")

    for idx, filename in enumerate(files, 1):
        file_path = os.path.join(IMPORT_FOLDER, filename)
        print(f"\n開始處理第 {idx}/{total_files} 個檔案：{filename}")

        try:
            import_single_file(file_path)
            print(f"  → {filename} 處理完成！")
        except Exception as e:
            print(f"  → {filename} 處理失敗：{str(e)}")
            continue

        frappe.db.commit()
        time.sleep(5)

    print("\n全部檔案處理完成！")

if __name__ == "__main__":
    import_all_files()