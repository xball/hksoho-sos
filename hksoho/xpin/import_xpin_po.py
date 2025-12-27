import os
import time
import pandas as pd
import frappe

# ===== 基本設定：請改成實際路徑 =====
BASE_PATH = "/home/frappe/frappe-bench/temp/xpin_import"
HEADER_FILE = os.path.join(BASE_PATH, "PO_Header.xlsx")
ITEMS_FILE = os.path.join(BASE_PATH, "PO_Order_Items.xlsx")
DOCS_FILE = os.path.join(BASE_PATH, "PO_Attached_Documents.xlsx")

# ===== 匯入主程式 =====

@frappe.whitelist()
def import_xpin_po_from_xlsx():
    """
    從三個 XLSX 檔匯入 / 更新 xpin_po + child tables
    """
    # 1. 讀 Excel
    print("Reading Excel files...")
    header_df = pd.read_excel(HEADER_FILE)
    print("Header file read.")
    items_df = pd.read_excel(ITEMS_FILE)
    print("Items file read.")
    docs_df = pd.read_excel(DOCS_FILE)
    print("Excel files read successfully.")
    # 確保欄位名稱都是小寫（和 Doctype 對應）
    header_df.columns = [c.strip().lower() for c in header_df.columns]
    items_df.columns = [c.strip().lower() for c in items_df.columns]
    docs_df.columns = [c.strip().lower() for c in docs_df.columns]
    print("Column names normalized.")
    # 轉成方便查詢的 dict：po_number -> 對應子表 rows
    items_by_po = {}
    if "po_number" in items_df.columns:
        for po_no, group in items_df.groupby("po_number"):
            items_by_po[po_no] = group.to_dict(orient="records")

    docs_by_po = {}
    if "po_number" in docs_df.columns:
        for po_no, group in docs_df.groupby("po_number"):
            docs_by_po[po_no] = group.to_dict(orient="records")
    print("Data grouped by PO number.")
    created = 0
    updated = 0

    # 2. 逐行處理 Header
    for _, row in header_df.iterrows():
        po_number = str(row.get("po_number") or "").strip()
        if not po_number:
            continue

        # 準備 parent 資料 dict
        parent_data = {
            "doctype": "xpin_po",
            "po_number": po_number,
            "buyer": row.get("buyer"),
            "supplier": row.get("supplier"),
            "dc": row.get("dc"),
            "origin_country": row.get("origin_country"),
            "origin_port": row.get("origin_port"),
            "destination_port": row.get("destination_port"),
            "purchaser": row.get("purchaser"),
            "responsible": row.get("responsible"),
            "order_type": row.get("order_type"),
            "purpose": row.get("purpose"),
            "po_status": row.get("po_status"),
            "delivery_status": row.get("delivery_status"),
            "payment_terms": row.get("payment_terms"),
            "delivery_terms": row.get("delivery_terms"),
            "delivery_mode": row.get("delivery_mode"),
            "equipment": row.get("equipment"),
            "requested_forwarder": row.get("requested_forwarder"),
            "booking_status": row.get("booking_status"),
            "qc_status": row.get("qc_status"),
            "consolidation": row.get("consolidation"),
            "transport_time": row.get("transport_time"),
            "routing": row.get("routing"),
            "order_placed": _safe_date(row.get("order_placed")),
            "finish_date": _safe_date(row.get("finish_date")),
            "po_ship_date": _safe_date(row.get("po_ship_date")),
            "sent_to_supplier": _safe_date(row.get("sent_to_supplier")),
            "supplier_confirmed": _safe_date(row.get("supplier_confirmed")),
            "production_started": _safe_date(row.get("production_started")),
            "requested_inspection": _safe_date(row.get("requested_inspection")),
            "booking_received": _safe_date(row.get("booking_received")),
            "requested_dc_eta": _safe_date(row.get("requested_dc_eta")),
            "calculated_dc_eta": _safe_date(row.get("calculated_dc_eta")),
            "available_at_wh": _safe_date(row.get("available_at_wh")),
            "loading_place": row.get("loading_place"),
            "supplier_address": row.get("supplier_address"),
            "buyer_address": row.get("buyer_address"),
            "delivery_address": row.get("delivery_address"),
            "html_filename": row.get("html_filename"),
        }

                # 將 parent_data 中所有 NaN 統一轉成 None
        for k, v in list(parent_data.items()):
            parent_data[k] = _nan_to_none(v)


        # 3. 判斷是新建還是更新
        existing_name = frappe.db.exists("xpin_po", {"po_number": po_number})
        if existing_name:
            doc = frappe.get_doc("xpin_po", existing_name)
            doc.update(parent_data)
            # 先清空舊子表
            doc.items = []
            doc.attached_docs = []
            updated += 1
        else:
            doc = frappe.get_doc(parent_data)
            created += 1

        # 4. 塞 items child table
        for item_row in items_by_po.get(po_number, []):
            child = doc.append("items", {})
            child.po_number = _nan_to_none(item_row.get("po_number"))
            child.line = _safe_int(item_row.get("line"))
            child.art_nr = _nan_to_none(item_row.get("art_nr"))
            child.article_name = _nan_to_none(item_row.get("article_name"))
            child.requested_ship_week = _nan_to_none(item_row.get("requested_ship_week"))
            child.requested_qty = _safe_int(item_row.get("requested_qty"))
            child.confirmed_ship_week = _nan_to_none(item_row.get("confirmed_ship_week"))
            child.confirmed_qty = _safe_int(item_row.get("confirmed_qty"))
            child.booked_qty = _safe_int(item_row.get("booked_qty"))
            child.qa = _safe_int(item_row.get("qa"))
            child.qr = _safe_int(item_row.get("qr"))
            child.updated_ship_week = _nan_to_none(item_row.get("updated_ship_week"))  # ★ 這裡是現在報錯的位置
            child.delivery_qty = _safe_int(item_row.get("delivery_qty"))
            child.remain_qty = _safe_int(item_row.get("remain_qty"))
            child.cbm = _safe_float(item_row.get("cbm"))
            child.gross_weight = _safe_float(item_row.get("gross_weight"))
            child.unit_price = _safe_float(item_row.get("unit_price"))
            child.amount = _safe_float(item_row.get("amount"))
            child.html_filename = _nan_to_none(item_row.get("html_filename"))

        # 5. 塞 attached_docs child table
        for doc_row in docs_by_po.get(po_number, []):
            child = doc.append("attached_docs", {})
            child.po_number = _nan_to_none(doc_row.get("po_number"))
            child.doc_type = _nan_to_none(doc_row.get("doc_type"))
            child.filename = _nan_to_none(doc_row.get("filename"))
            child.docid = _nan_to_none(doc_row.get("data_docid"))
            child.file_size = _nan_to_none(doc_row.get("file_size"))
            child.uploaded = _safe_date(doc_row.get("uploaded"))
            child.art_number = _nan_to_none(doc_row.get("art_number"))
            child.html_filename = _nan_to_none(doc_row.get("html_filename"))

        # 6. 寫入 DB
        doc.save(ignore_permissions=True)
        if (created + updated) % 100 == 0:
            frappe.db.commit()
            print(f"Imported/Updated {created + updated} xpin_po records...")
            time.sleep(3)
            

    frappe.db.commit()
    return {
        "created": created,
        "updated": updated,
    }


# ===== 小工具：安全轉型 =====

def _safe_int(v):
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return int(str(v).replace(",", ""))
    except Exception:
        return None

def _safe_float(v):
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return float(str(v).replace(",", ""))
    except Exception:
        return None

def _safe_date(v):
    """
    支援 Excel 讀出來的 datetime / string / NaT 轉 frappe 接受的 yyyy-mm-dd 字串
    """
    if pd.isna(v):
        return None
    try:
        # 如果本身就是 datetime / Timestamp
        if hasattr(v, "date"):
            return v.date().isoformat()
        # 若是字串，讓 pandas 幫忙 parse
        s = str(v).strip()
        if not s:
            return None
        d = pd.to_datetime(s, errors="coerce")
        if pd.isna(d):
            return None
        return d.date().isoformat()
    except Exception:
        return None

def _nan_to_none(v):
    """把 pandas 的 NaN 統一轉成 None"""
    import math
    try:
        # pandas 的 NaN / numpy.nan 都會被 float(...) 轉成 float
        if v is None:
            return None
        # pandas NaT 也要處理
        import pandas as pd
        if isinstance(v, (pd._libs.tslibs.nattype.NaTType, )):
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    return v
