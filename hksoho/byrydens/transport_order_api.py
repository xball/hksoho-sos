import frappe
from frappe import _
import json

@frappe.whitelist()
def get_po_items(po_name, filters=None):
    """Return all items for the specified Purchase Order where workflow_state is 'Ready to Ship' and qty > 0"""
    if not po_name:
        frappe.throw("Please provide a valid Purchase Order number")

    try:
        # Check if the Purchase Order has workflow_state = 'Ready to Ship'
        po = frappe.get_doc("Purchase Order", po_name)
        if po.workflow_state != "Ready to Ship" and po.workflow_state != 'Partial Shipout':
            frappe.msgprint({
                "title": "No Data",
                "message": f"The Purchase Order {po_name} does not have workflow_state 'Ready to Ship'.",
                "indicator": "orange"
            })
            return []

        # Initialize filters for Purchase Order Item
        filters = filters or {}
        filters['parent'] = po_name

        # Fetch items with necessary fields
        items = frappe.get_all(
            "Purchase Order Item",
            filters=filters,
            fields=["name", "line", "article_number", "article_name", "booked_qty", "delivery_qty", "ctns_on_pallet", "carton_cbm", "carton_gross_kg", "unit_price"],
            order_by="line asc"
        )

        # Filter items where qty = booked_qty - delivery_qty > 0
        filtered_items = [
            item for item in items
            if (item.get('booked_qty', 0) - item.get('delivery_qty', 0)) > 0
        ]

        if not filtered_items:
            frappe.msgprint({
                "title": "No Data",
                "message": "No items found for the specified Purchase Order with qty > 0.",
                "indicator": "orange"
            })

        return filtered_items
    except frappe.DoesNotExistError:
        frappe.throw(f"Purchase Order {po_name} does not exist.")
    except frappe.PermissionError:
        frappe.throw("You do not have sufficient permissions to access Purchase Order items. Please contact your administrator for access.", frappe.PermissionError)
    except Exception as e:
        frappe.log_error(f"Error fetching PO items for {po_name}: {str(e)}")
        frappe.throw(f"Failed to fetch Purchase Order items. Please try again later. Error: {str(e)}")
        
        


@frappe.whitelist()
def update_to_line_invoice(to_name, po_number, invoice_data):
    """
    Update invoice details for Transport Order Line items matching the given po_number and save the Transport Order.

    Args:
        to_name (str): Name of the Transport Order
        po_number (str): Selected Purchase Order number
        invoice_data (str or dict): Dictionary or JSON string containing invoice details, e.g.:
            {
                "invoice_received": 1,
                "invoice_no": "INV-20251003",
                "invoice_currency": "USD",
                "invoice_date": "2025-10-03",
                "invoice_due_date": "2025-11-03",
                "invoice_paid": 0,
                "exchange_rate_to_sek": 10.5
            }
    Returns:
        dict: Result message indicating success or failure
    """
    try:
        if not frappe.has_permission("Transport Order", "write", to_name):
            frappe.throw(_("You do not have permission to update this Transport Order."), frappe.PermissionError)

        # Parse invoice_data if it's a string
        if isinstance(invoice_data, str):
            invoice_data = json.loads(invoice_data)
        elif not isinstance(invoice_data, dict):
            frappe.throw(_("Invalid invoice_data format. Expected a dictionary or JSON string."))

        # Get Transport Order
        to_doc = frappe.get_doc("Transport Order", to_name)

        # Validate po_line links
        invalid_lines = []
        for item in to_doc.items:
            if item.po_number == po_number and item.po_line:
                if not frappe.db.exists("Purchase Order Item", item.po_line):
                    invalid_lines.append(f"Row #{item.idx}: PO Line: {item.po_line}")

        if invalid_lines:
            frappe.throw(_("Could not find the following PO Line references: {0}").format(", ".join(invalid_lines)))

        # Validate invoice data
        if invoice_data.get("invoice_received") and invoice_data.get("invoice_date") and invoice_data.get("invoice_due_date"):
            if invoice_data["invoice_due_date"] < invoice_data["invoice_date"]:
                frappe.throw(_("Invoice Due Date cannot be earlier than Invoice Date."))

        updated = False
        # Update Transport Order Line
        for item in to_doc.items:
            if item.po_number == po_number:
                item.invoice_received = invoice_data.get("invoice_received", 0)
                if item.invoice_received:
                    item.invoice_no = invoice_data.get("invoice_no")
                    item.invoice_currency = invoice_data.get("invoice_currency")
                    item.invoice_date = invoice_data.get("invoice_date")
                    item.invoice_due_date = invoice_data.get("invoice_due_date")
                    item.invoice_paid = invoice_data.get("invoice_paid", 0)
                    item.exchange_rate_to_sek = invoice_data.get("exchange_rate_to_sek")
                else:
                    item.invoice_no = None
                    item.invoice_currency = None
                    item.invoice_date = None
                    item.invoice_due_date = None
                    item.invoice_paid = 0
                    item.exchange_rate_to_sek = None
                updated = True

        if not updated:
            frappe.throw(_("No items found matching the selected Purchase Order: {0}").format(po_number))

        # Save Transport Order
        to_doc.save()

        return {
            "status": "success",
            "message": "Invoice details updated and form saved successfully!"
        }

    except Exception as e:
        # Truncate error message to avoid CharacterLengthExceededError
        error_message = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        frappe.log_error(f"Failed to update Transport Order Line: {error_message}", "Update TO Line Invoice")
        return {
            "status": "error",
            "message": f"Failed to update invoice details: {error_message}"
        }

from datetime import timedelta
import logging

logger = logging.getLogger("update_vessel_dates")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    log_file = frappe.get_site_path("logs", "update_vessel_dates.log")
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


@frappe.whitelist()
def update_vessel_dates(vessel_name, cfs_close=None, etd_date=None, eta_date=None,
                        dest_port_free_days=0, to_name=None):
    if not frappe.has_permission("Vessels Time Table", "write", vessel_name):
        frappe.throw(_("You do not have permission to update this vessel schedule."), frappe.PermissionError)
    if to_name and not frappe.has_permission("Transport Order", "write", to_name):
        frappe.throw(_("You do not have permission to update this Transport Order."), frappe.PermissionError)

    logger.debug("=== update_vessel_dates 開始執行 ===")
    logger.debug(f"Vessel: {vessel_name} | TO: {to_name} | ETA Date: {eta_date}")

    # 1. 更新 Vessels Time Table
    vessel_doc = frappe.get_doc("Vessels Time Table", vessel_name)
    vessel_doc.cfs_close = cfs_close
    vessel_doc.etd_date = etd_date
    vessel_doc.eta_date = eta_date
    vessel_doc.dest_port_free_days = dest_port_free_days
    vessel_doc.save()
    logger.debug("Vessels Time Table 已更新")

    # 2. 更新相關 PO Item 的 confirmed_shipdate
    updated_items = 0
    if to_name and eta_date:
        logger.debug(f"開始更新 Transport Order [{to_name}] 相關 PO 的 confirmed_shipdate")

        to_doc = frappe.get_doc("Transport Order", to_name)
        logger.debug(f"🔍 TO [{to_name}] 共有 {len(to_doc.items)} 個 items")

        eta_date_obj = frappe.utils.getdate(eta_date)
        new_confirmed_shipdate = eta_date_obj - timedelta(days=60)
        logger.debug(f"新的 Confirmed Ship Date: {new_confirmed_shipdate}")

        po_docs_to_save = {}

        for line in to_doc.items:
            logger.debug(f"🔍 TO Line: {line.name}, po_line: {getattr(line, 'po_line', 'None')}")
            if not line.po_line:
                continue

            po_name = frappe.db.get_value("Purchase Order Item", line.po_line, "parent")
            if not po_name:
                logger.warning(f"TO Line {line.name} 的 po_line {line.po_line} 無對應 PO")
                continue

            logger.debug(f"處理 TO Line [{line.name}] po_line={line.po_line} → PO={po_name}")

            if po_name not in po_docs_to_save:
                if not frappe.has_permission("Purchase Order", "write", po_name):
                    logger.warning(f"Skipping PO [{po_name}] — no write permission")
                    continue
                po_docs_to_save[po_name] = frappe.get_doc("Purchase Order", po_name)

            po_doc = po_docs_to_save[po_name]
            logger.debug(f"PO [{po_name}] 共有 {len(po_doc.po_items)} 個 po_items")
            found_match = False

            for idx, item in enumerate(po_doc.po_items):
                if str(item.name) == str(line.po_line):
                    old_value = item.confirmed_shipdate
                    logger.debug(
                        f"##PO [{po_name}] 的 Item [{item.name}] "
                        f"confirmed_shipdate 更新: {old_value} → {new_confirmed_shipdate}"
                    )
                    item.confirmed_shipdate = new_confirmed_shipdate
                    updated_items += 1
                    found_match = True
                    break

            if not found_match:
                logger.warning(f"❌ PO [{po_name}] 中找不到 po_line = {line.po_line}")

        update_count = 0
        for po_name, po_doc in po_docs_to_save.items():
            try:
                po_doc.save()
                logger.debug(f"Purchase Order [{po_name}] 已儲存")
                update_count += 1
            except Exception as e:
                logger.error(f"儲存 Purchase Order [{po_name}] 失敗: {str(e)}")

        logger.debug(f"總共更新 {updated_items} 個 Item，儲存 {update_count} 筆 PO")

    # 3. 更新 Transport Order 本身欄位
    if to_name:
        updates = {}
        if cfs_close:
            updates["cfs_close"] = cfs_close
        if etd_date:
            updates["etd_date"] = etd_date
        if eta_date:
            updates["eta_date"] = eta_date
            updates["dest_port_free_days"] = int(dest_port_free_days)

        if updates:
            frappe.db.set_value("Transport Order", to_name, updates)
            logger.debug(f"Transport Order [{to_name}] 已更新（CFS/ETD/ETA/Free Days）")

    logger.debug("=== update_vessel_dates 執行完畢 ===")
    return {"status": "success", "updated_items": updated_items}


@frappe.whitelist()
def fix_po_item_order_status_for_shipped_to(dry_run=False, reset_status_to=""):
    """
    清理錯誤標記為 Shipped 的 Purchase Order Item.order_status。
    只保留「在 workflow_state = 'Shipped' 的 Transport Order Line 上」那些 PO Item 為 Shipped。
    
    :param dry_run: True = 只列出會被更新的資料，不真的寫入 DB
    :param reset_status_to: 要改回的值，例如 "" 或 "Pending"
    """
    frappe.only_for("System Manager")
    logger = frappe.logger("to_po_fix")

    # 1. 找出所有 workflow_state = 'Shipped' 的 Transport Order
    shipped_to_names = frappe.get_all(
        "Transport Order",
        filters={"workflow_state": "Shipped"},
        pluck="name"
    )
    logger.info(f"找到 {len(shipped_to_names)} 筆 Shipped 狀態的 TO")

    # 2. 收集這些 TO Line 上的 po_line (= PO Item.name)
    valid_po_item_names = set()
    if shipped_to_names:
        to_lines = frappe.get_all(
            "Transport Order Line",
            filters={"parent": ["in", shipped_to_names]},
            fields=["name", "parent", "po_line"]
        )
        for line in to_lines:
            if line.po_line:
                valid_po_item_names.add(str(line.po_line))

    logger.info(f"在 Shipped TO Line 中，共有 {len(valid_po_item_names)} 筆 PO Item 應為 Shipped")

    # 3. 找出目前 order_status = 'Shipped' 的所有 PO Item
    shipped_po_items = frappe.get_all(
        "Purchase Order Item",
        filters={"order_status": "Shipped"},
        fields=["name", "parent", "order_status"]
    )
    logger.info(f"目前資料庫中，order_status = 'Shipped' 的 PO Item 共 {len(shipped_po_items)} 筆")

    # 4. 過濾出「不在 valid_po_item_names 中」的 → 代表應該被清掉
    to_reset = []
    for row in shipped_po_items:
        if str(row.name) not in valid_po_item_names:
            to_reset.append(row)

    logger.info(f"其中有 {len(to_reset)} 筆 PO Item 的 Shipped 狀態是多餘的，將被重設為 '{reset_status_to}'")

    if dry_run:
        for r in to_reset[:200]:
            logger.info(f"[DRY RUN] 會被重設的 PO Item: {r.name} (PO: {r.parent})")
        return {
            "dry_run": True,
            "to_reset_count": len(to_reset),
        }

    # 5. 實際更新這些錯誤的 PO Item
    for r in to_reset:
        frappe.db.set_value(
            "Purchase Order Item",
            r.name,
            "order_status",
            reset_status_to
        )

    frappe.db.commit()
    logger.info(f"實際已重設 {len(to_reset)} 筆 PO Item.order_status 為 '{reset_status_to}'")

    return {
        "dry_run": False,
        "reset_to": reset_status_to,
        "affected_rows": len(to_reset),
    }


@frappe.whitelist()
def fix_po_item_order_status_and_trigger_before_save(dry_run=True, reset_status_to=""):
    """
    1) 找出所有 order_status = 'Shipped' 的 Purchase Order Item
    2) 只保留「有在 workflow_state = 'Shipped' 的 Transport Order Line 上」那幾筆
    3) 其他多餘的改回 reset_status_to
    4) 對受影響的 Purchase Order 呼叫 save()，觸發 before_save
    """
    frappe.only_for("System Manager")
    logger = frappe.logger("to_po_fix")

    # -------------------------------
    # A. 收集 Shipped TO Line 對應的 PO Item（真正應該是 Shipped 的）
    # -------------------------------
    shipped_to_names = frappe.get_all(
        "Transport Order",
        filters={"workflow_state": "Shipped"},
        pluck="name"
    )
    logger.info(f"[FIX] 找到 {len(shipped_to_names)} 筆 Shipped 狀態的 TO")

    valid_po_item_names = set()
    if shipped_to_names:
        to_lines = frappe.get_all(
            "Transport Order Line",
            filters={"parent": ["in", shipped_to_names]},
            fields=["name", "parent", "po_line"]
        )
        for line in to_lines:
            if line.po_line:
                valid_po_item_names.add(str(line.po_line))

    logger.info(f"[FIX] 在 Shipped TO Line 中，共有 {len(valid_po_item_names)} 筆 PO Item 應為 Shipped")

    # -------------------------------
    # B. 找出目前被標為 Shipped 的 PO Item
    # -------------------------------
    shipped_po_items = frappe.get_all(
        "Purchase Order Item",
        filters={"order_status": "Shipped"},
        fields=["name", "parent", "order_status"]
    )
    logger.info(f"[FIX] 目前資料庫中，order_status = 'Shipped' 的 PO Item 共 {len(shipped_po_items)} 筆")

    # -------------------------------
    # C. 篩出「不在 valid_po_item_names 中」的 → 應該被還原
    # -------------------------------
    to_reset = []
    affected_po_names = set()

    for row in shipped_po_items:
        if str(row.name) not in valid_po_item_names:
            to_reset.append(row)
            affected_po_names.add(row.parent)

    logger.info(
        f"[FIX] 其中有 {len(to_reset)} 筆 PO Item 的 Shipped 狀態是多餘的，"
        f"將被重設為 '{reset_status_to}'，影響 {len(affected_po_names)} 張 PO"
    )

    if dry_run:
        # 只列出前 200 筆預覽
        for r in to_reset[:200]:
            logger.info(f"[DRY RUN] 將重設 PO Item: {r.name} (PO: {r.parent})")
        return {
            "dry_run": True,
            "to_reset_count": len(to_reset),
            "affected_po_count": len(affected_po_names),
        }

    # -------------------------------
    # D. 實際更新這些錯誤的 PO Item.order_status
    # -------------------------------
    for r in to_reset:
        frappe.db.set_value(
            "Purchase Order Item",
            r.name,
            "order_status",
            reset_status_to
        )

    logger.info(f"[FIX] 已重設 {len(to_reset)} 筆 PO Item.order_status 為 '{reset_status_to}'")

    # -------------------------------
    # E. 逐張觸發對應 PO 的 before_save
    #    方式與你 TO before_save 裡的一樣，用 flag 防無限 loop
    # -------------------------------
    for po_name in affected_po_names:
        try:
            po_doc = frappe.get_doc("Purchase Order", po_name)
            if not frappe.flags.get("in_to_sync"):
                frappe.flags.in_to_sync = True
                po_doc.save()   # ⬅ 這裡會觸發 Purchase Order.before_save
                frappe.flags.in_to_sync = False
            logger.info(f"[FIX] 已觸發 PO {po_name} 的 before_save")
        except Exception as e:
            logger.error(f"[FIX] 觸發 PO {po_name} before_save 失敗: {str(e)}")
            frappe.log_error(
                f"Failed to trigger before_save for PO {po_name}: {str(e)}",
                "TO → PO Fix Script"
            )

    frappe.db.commit()
    logger.info(
        f"[FIX] 完成修正，共重設 {len(to_reset)} 筆 PO Item，"
        f"觸發 {len(affected_po_names)} 張 PO 的 before_save"
    )

    return {
        "dry_run": False,
        "reset_to": reset_status_to,
        "reset_item_count": len(to_reset),
        "triggered_po_count": len(affected_po_names),
    }






def check_po_qty(dry_run=True):
    valid_states = ['Confirmed', 'Shipped', 'ETA Passed', 'Arrived', 'Undelivered', 'Delivered']
    po_items = frappe.get_all("Purchase Order Item", 
                              fields=["name", "confirmed_qty", "booked_qty", "delivery_qty", "remaining_qty"])
    
    problems = []
    
    for item in po_items:
        # 計算所有有效 TO 的總出貨量
        calc_delivery = frappe.db.sql("""
            SELECT SUM(tol.qty) 
            FROM `tabTransport Order Line` tol
            INNER JOIN `tabTransport Order` tor ON tol.parent = tor.name
            WHERE tol.po_line = %s 
            AND tor.workflow_state IN %s
        """, (item.name, tuple(valid_states)))[0][0] or 0
        
        # 新公式：remaining 以 confirmed_qty 為基準
        calc_remaining = max(0, (item.confirmed_qty or 0) - calc_delivery)
        
        has_issue = (
            item.delivery_qty != calc_delivery or
            item.remaining_qty != calc_remaining or
            calc_delivery > (item.confirmed_qty or 0)  # 檢查超額出貨
        )
        
        if has_issue:
            problems.append({
                'name': item.name,
                'confirmed_qty': item.confirmed_qty or 0,
                'booked_qty': item.booked_qty or 0,
                'current_delivery': item.delivery_qty,
                'should_delivery': calc_delivery,
                'current_remaining': item.remaining_qty,
                'should_remaining': calc_remaining,
                'over_delivery': calc_delivery > (item.confirmed_qty or 0)
            })
    
    if not problems:
        print("所有 PO Item 數值正確，無需修正")
        return
    
    print(f"\n找到 {len(problems)} 筆有問題的 PO Item：\n")
    for p in problems:
        print(f"PO Item: {p['name']}")
        print(f"  confirmed_qty : {p['confirmed_qty']}")
        print(f"  booked_qty    : {p['booked_qty']}")
        print(f"  delivery → 目前: {p['current_delivery']} | 應為: {p['should_delivery']}")
        if p['over_delivery']:
            print("  ※ 注意：delivery_qty 已超過 confirmed_qty（超額出貨）")
        print(f"  remaining → 目前: {p['current_remaining']} | 應為: {p['should_remaining']}")
        print("-" * 80 + "\n")
    
    if dry_run:
        print("※ 目前為檢查模式，未更新資料庫。請確認後再執行更新。")
    # 若要更新，可在此加入 frappe.db.set_value 邏輯

# 執行方式（在 bench console）
# check_po_qty(dry_run=True)


def check_specific_po_items():
    # 只檢查這 5 筆有嚴重問題的 PO Item
    target_names = ['508', '509', '510', '511', '512']
    
    valid_states = ['Confirmed', 'Shipped', 'ETA Passed', 'Arrived', 'Undelivered', 'Delivered']
    
    po_items = frappe.get_all("Purchase Order Item",
                              filters=[["name", "in", target_names]],
                              fields=["name", "confirmed_qty", "booked_qty", "delivery_qty", "remaining_qty"])
    
    print(f"正在檢查 {len(po_items)} 筆指定 PO Item：{target_names}\n")
    
    for item in po_items:
        calc_delivery = frappe.db.sql("""
            SELECT SUM(tol.qty) 
            FROM `tabTransport Order Line` tol
            INNER JOIN `tabTransport Order` tor ON tol.parent = tor.name
            WHERE tol.po_line = %s 
            AND tor.workflow_state IN %s
        """, (item.name, tuple(valid_states)))[0][0] or 0
        
        # remaining_qty 以 confirmed_qty 為基準（依您最新說明）
        calc_remaining = max(0, (item.confirmed_qty or 0) - calc_delivery)
        
        print(f"PO Item: {item.name}")
        print(f"  confirmed_qty : {item.confirmed_qty or 0}")
        print(f"  booked_qty    : {item.booked_qty or 0}")
        print(f"  目前 delivery_qty : {item.delivery_qty or 0}")
        print(f"  應有 delivery_qty : {calc_delivery}")
        print(f"  目前 remaining_qty: {item.remaining_qty or 0}")
        print(f"  應有 remaining_qty: {calc_remaining}")
        if calc_delivery > (item.confirmed_qty or 0):
            print("  ※ 警告：delivery_qty 已超過 confirmed_qty（超額出貨）")
        print("-" * 80 + "\n")

