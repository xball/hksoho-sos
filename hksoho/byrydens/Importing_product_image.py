# -*- coding: utf-8 -*-
import frappe
import pandas as pd
import os
import time
import gc
from pathlib import Path
from glob import glob

IMAGE_ROOT = "/home/frappe/frappe-bench/temp"
RESUME_FILE = "/home/frappe/frappe-bench/temp/product_image_resume_ultimate.json"
PRODUCTS_FOLDER = "Home/Attachments"

def save_progress(idx):
    with open(RESUME_FILE, "w") as f:
        f.write(str(idx))

def get_last_index():
    if os.path.exists(RESUME_FILE):
        try:
            with open(RESUME_FILE) as f:
                return int(f.read().strip())
        except:
            return -1
    return -1

def ensure_folder(path):
    folder_name = path.split("/")[-1]
    parent = "/".join(path.split("/")[:-1])
    if not frappe.db.exists("File", {"file_name": folder_name, "is_folder": 1, "folder": parent}):
        folder_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": folder_name,
            "is_folder": 1,
            "folder": parent,
        })
        folder_doc.flags.ignore_permissions = True
        folder_doc.insert()
        frappe.db.commit()
        print(f"Created folder {path}")

def get_image_file_path(image_file_field):
    # Returns absolute path and tries all jpg case variants
    abs_base = os.path.join(IMAGE_ROOT, image_file_field.lstrip("/"))
    base_no_ext, ext = os.path.splitext(abs_base)
    extensions = [".jpg", ".JPG", ".Jpg", ".jPg", ".jpG"]  # Extend if needed
    for ext_case in extensions:
        candidate = base_no_ext + ext_case
        if os.path.isfile(candidate):
            return candidate
    # Also try glob as fallback
    matches = glob(base_no_ext + ".jp*")
    return matches[0] if matches else None

def run_import(excel_path=None):
    frappe.flags.in_migrate = True
    if not excel_path:
        excel_path = "/home/frappe/frappe-bench/temp/product_images_A.xlsx"

    ensure_folder(PRODUCTS_FOLDER)

    df = pd.read_excel(excel_path)
    total = len(df)
    start_from = get_last_index() + 1

    print("\n" + "="*100)
    print("【2025-11-25 v15 Product Image Import】")
    print(f"Total {total} records, starting from {start_from+1}")
    print("="*100 + "\n")

    success = updated = failed = 0

    for idx in range(start_from, total):
        row = df.iloc[idx]
        article = str(row["article_number"]).strip()
        image_field = str(row["Image_file"]).strip()

        try:
            image_path = get_image_file_path(image_field)
            if not image_path:
                print(f"Skip: {article} → Image not found for path {image_field}")
                failed += 1
                save_progress(idx)
                continue

            print(f"Match found → {article} uses {os.path.basename(image_path)} (in {os.path.dirname(image_path)})")

            # Delete old image
            old_file_url = frappe.db.get_value("Product", article, "primary_image")
            if old_file_url:
                old_file = frappe.get_all("File", filters={"file_url": old_file_url}, limit=1)
                if old_file:
                    doc_old = frappe.get_doc("File", old_file[0]["name"])
                    doc_old.delete()
                    frappe.db.commit()
                    print(f"Deleted old image file for {article}")

            # Upload new image
            with open(image_path, "rb") as f:
                content = f.read()

            filedoc = frappe.get_doc({
                "doctype": "File",
                "file_name": os.path.basename(image_path),
                "folder": PRODUCTS_FOLDER,
                "is_private": 0,
                "content": content,
            })

            filedoc.flags.ignore_permissions = True
            filedoc.flags.ignore_mandatory = True
            filedoc.flags.ignore_validate = True
            filedoc.flags.ignore_file_validation = True

            filedoc.save()
            frappe.db.commit()

            # Update product record
            old = frappe.db.get_value("Product", article, "primary_image")
            frappe.db.set_value("Product", article, "primary_image", filedoc.file_url)
            frappe.db.commit()

            if not old:
                success += 1
                print(f"【Success】Added primary image → {article}")
            else:
                updated += 1
                print(f"【Success】Replaced primary image → {article}")

            content = None
            gc.collect()
            save_progress(idx)

            cur = idx - start_from + 1
            print(f"   → Record {cur} | Progress {idx+1}/{total} | Total Success {success + updated}\n")

            if cur % 20 == 0:
                print("="*90)
                print(f"Progress checkpoint: processed {cur} records | Success {success + updated}")
                print("="*90 + "\n")

        except Exception as e:
            failed += 1
            print(f"✘ Failed: {article} → {str(e)}\n")
            save_progress(idx)

        time.sleep(0.05)

    if os.path.exists(RESUME_FILE):
        os.remove(RESUME_FILE)

    frappe.clear_cache()
    print("\n" + "="*100)
    print("【All Done】Product primary image import completed!")
    print(f"Added {success} | Replaced {updated} | Failed {failed}")
    print("="*100)

    frappe.msgprint("All primary images imported successfully!", title="Import Complete", indicator="green")

if __name__ == "__main__":
    run_import()
