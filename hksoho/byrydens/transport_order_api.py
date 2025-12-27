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
        to_doc.save(ignore_permissions=True)
        frappe.db.commit()

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
        
import frappe
from datetime import timedelta
import logging

# 設定自訂 log file（會寫在 sites 目錄下，每個 site 獨立）
logger = logging.getLogger('update_vessel_dates')
logger.setLevel(logging.DEBUG)

# 避免重複添加 handler
if not logger.handlers:
    log_file = frappe.get_site_path('logs', 'update_vessel_dates.log')
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

@frappe.whitelist()
def update_vessel_dates1(vessel_name, cfs_close=None, etd_date=None, eta_date=None, dest_port_free_days=0, to_name=None):
    # 寫入自訂 log file
    logger.debug("=== update_vessel_dates 開始執行 ===")
    logger.debug(f"Vessel: {vessel_name} | TO: {to_name} | ETA Date: {eta_date}")

    # 1. 更新 Vessels Time Table
    vessel_doc = frappe.get_doc('Vessels Time Table', vessel_name)
    vessel_doc.cfs_close = cfs_close
    vessel_doc.etd_date = etd_date
    vessel_doc.eta_date = eta_date
    vessel_doc.dest_port_free_days = dest_port_free_days
    vessel_doc.save(ignore_permissions=True)
    logger.debug("Vessels Time Table 已更新")

    # 2. 更新相關 PO Item 的 confirmed_shipdate（觸發 before_save）
    if to_name and eta_date:
        logger.debug(f"開始更新 Transport Order [{to_name}] 相關 PO 的 confirmed_shipdate")
        
        to_doc = frappe.get_doc('Transport Order', to_name)
        logger.debug(f"🔍 TO [{to_name}] 共有 {len(to_doc.items)} 個 items")  # ← 新增這行
        
        eta_date_obj = frappe.utils.getdate(eta_date)
        new_confirmed_shipdate = eta_date_obj - timedelta(days=60)
        logger.debug(f"新的 Confirmed Ship Date: {new_confirmed_shipdate}")

        po_docs_to_save = {}
        updated_items = 0

        for line in to_doc.items:
            logger.debug(f"🔍 TO Line: {line.name}, po_line: {getattr(line, 'po_line', 'None')}")
            if line.po_line:
                po_name = frappe.db.get_value('Purchase Order Item', line.po_line, 'parent')
                if not po_name:
                    logger.warning(f"TO Line {line.name} 的 po_line {line.po_line} 無對應 PO")
                    continue

                logger.debug(f"處理 TO Line [{line.name}] po_line={line.po_line} → PO={po_name}")

                if po_name not in po_docs_to_save:
                    po_docs_to_save[po_name] = frappe.get_doc('Purchase Order', po_name)

                po_doc = po_docs_to_save[po_name]

                # **加強偵錯：列出所有 PO Items**
                logger.debug(f"PO [{po_name}] 共有 {len(po_doc.po_items)} 個 items")
                found_match = False
                
                for idx, item in enumerate(po_doc.po_items):
                    logger.debug(f"  PO Item {idx}: name={item.name}, article={getattr(item, 'article_number', 'N/A')}")
                    if item.name == line.po_line:
                        old_value = item.confirmed_shipdate
                        logger.debug(f"##PO [{po_name}] 的 Item [{item.name}] confirmed_shipdate 更新: {old_value} → {new_confirmed_shipdate}")
                        
                        item.confirmed_shipdate = new_confirmed_shipdate
                        updated_items += 1
                        found_match = True
                        logger.debug(f"✓ 已更新 PO [{po_name}] Item [{item.name}]")
                        break
                
                if not found_match:
                    logger.warning(f"❌ PO [{po_name}] 中找不到 po_line = {line.po_line}")

        # 儲存 PO...
        update_count = 0
        for po_name, po_doc in po_docs_to_save.items():
            try:
                po_doc.save(ignore_permissions=True)
                logger.debug(f"Purchase Order [{po_name}] 已儲存")
                update_count += 1
            except Exception as e:
                logger.error(f"儲存 PO [{po_name}] 失敗: {str(e)}")

        logger.debug(f"總共更新 {updated_items} 個 Item，儲存 {update_count} 筆 PO")
    

@frappe.whitelist()
def update_vessel_dates(vessel_name, cfs_close=None, etd_date=None, eta_date=None,
                        dest_port_free_days=0, to_name=None):
    logger.debug("=== update_vessel_dates 開始執行 ===")
    logger.debug(f"Vessel: {vessel_name} | TO: {to_name} | ETA Date: {eta_date}")

    # 1. 更新 Vessels Time Table
    vessel_doc = frappe.get_doc('Vessels Time Table', vessel_name)
    vessel_doc.cfs_close = cfs_close
    vessel_doc.etd_date = etd_date
    vessel_doc.eta_date = eta_date
    vessel_doc.dest_port_free_days = dest_port_free_days
    vessel_doc.save(ignore_permissions=True)
    logger.debug("Vessels Time Table 已更新")

    # 2. 更新相關 PO Item 的 confirmed_shipdate
    updated_items = 0
    if to_name and eta_date:
        logger.debug(f"開始更新 Transport Order [{to_name}] 相關 PO 的 confirmed_shipdate")

        to_doc = frappe.get_doc('Transport Order', to_name)
        logger.debug(f"🔍 TO [{to_name}] 共有 {len(to_doc.items)} 個 items")

        eta_date_obj = frappe.utils.getdate(eta_date)
        new_confirmed_shipdate = eta_date_obj - timedelta(days=60)
        logger.debug(f"新的 Confirmed Ship Date: {new_confirmed_shipdate}")

        po_docs_to_save = {}

        for line in to_doc.items:
            logger.debug(f"🔍 TO Line: {line.name}, po_line: {getattr(line, 'po_line', 'None')}")
            if not line.po_line:
                continue

            # 取出 PO name（parent）
            po_name = frappe.db.get_value('Purchase Order Item', line.po_line, 'parent')
            if not po_name:
                logger.warning(f"TO Line {line.name} 的 po_line {line.po_line} 無對應 PO")
                continue

            logger.debug(f"處理 TO Line [{line.name}] po_line={line.po_line} → PO={po_name}")

            if po_name not in po_docs_to_save:
                po_docs_to_save[po_name] = frappe.get_doc('Purchase Order', po_name)

            po_doc = po_docs_to_save[po_name]

            # ✅ 注意：這裡要用 po_items，不是 items
            logger.debug(f"PO [{po_name}] 共有 {len(po_doc.po_items)} 個 po_items")
            found_match = False

            for idx, item in enumerate(po_doc.po_items):
                logger.debug(
                    f"  PO Item {idx}: name={item.name}, article={getattr(item, 'article_number', 'N/A')}"
                )
                logger.debug(
                    f"    比對用 → item.name={item.name} ({type(item.name)}), "
                    f"po_line={line.po_line} ({type(line.po_line)})"
                )

                # ✅ 統一用字串比對，避免 '683' vs 683 型別不一致
                if str(item.name) == str(line.po_line):
                    old_value = item.confirmed_shipdate
                    logger.debug(
                        f"##PO [{po_name}] 的 Item [{item.name}] "
                        f"confirmed_shipdate 更新: {old_value} → {new_confirmed_shipdate}"
                    )

                    item.confirmed_shipdate = new_confirmed_shipdate
                    updated_items += 1
                    found_match = True
                    logger.debug(f"✓ 已更新 PO [{po_name}] Item [{item.name}]")
                    break

            if not found_match:
                logger.warning(f"❌ PO [{po_name}] 中找不到 po_line = {line.po_line}")

        # 儲存所有有被修改過的 PO
        update_count = 0
        for po_name, po_doc in po_docs_to_save.items():
            try:
                po_doc.save(ignore_permissions=True)
                logger.debug(f"Purchase Order [{po_name}] 已儲存")
                update_count += 1
            except Exception as e:
                logger.error(f"儲存 Purchase Order [{po_name}] 失敗: {str(e)}")

        logger.debug(f"總共更新 {updated_items} 個 Item，儲存 {update_count} 筆 PO")

    # 3. 更新 Transport Order 本身欄位（如果需要）
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

    frappe.db.commit()
    logger.debug("=== update_vessel_dates 執行完畢 ===")
    return {"status": "success", "updated_items": updated_items}



# 2. 更新 Transport Order → 改用 set_value 強制寫入（完全無視 workflow 凍結）
    if to_name:
        updates = {}
        if cfs_close:          
            updates["cfs_close"] = cfs_close
        if etd_date:           
            updates["etd_date"] = etd_date
            #updates["booked_etd"] = etd_date
        if eta_date:           
            updates["eta_date"] = eta_date
            updates["dest_port_free_days"] = int(dest_port_free_days)

        frappe.db.set_value("Transport Order", to_name, updates)

    frappe.db.commit()
    return {"status": "success"}
    


@frappe.whitelist()
def fix_po_item_order_status_for_shipped_to(dry_run=False, reset_status_to=""):
    """
    清理錯誤標記為 Shipped 的 Purchase Order Item.order_status。
    只保留「在 workflow_state = 'Shipped' 的 Transport Order Line 上」那些 PO Item 為 Shipped。
    
    :param dry_run: True = 只列出會被更新的資料，不真的寫入 DB
    :param reset_status_to: 要改回的值，例如 "" 或 "Pending"
    """
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

    # if dry_run:
    #     # 只印出名單，不動資料
    #     for r in to_reset[:200]:
    #         logger.info(f"[DRY RUN] 會被重設的 PO Item: {r.name} (PO: {r.parent})")
    #     return {
    #         "dry_run": True,
    #         "to_reset_count": len(to_reset)
    #     }

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
        "affected_rows": len(to_reset)
    }


import frappe

@frappe.whitelist()
def fix_po_item_order_status_and_trigger_before_save(dry_run=True, reset_status_to=""):
    """
    1) 找出所有 order_status = 'Shipped' 的 Purchase Order Item
    2) 只保留「有在 workflow_state = 'Shipped' 的 Transport Order Line 上」那幾筆
    3) 其他多餘的改回 reset_status_to
    4) 對受影響的 Purchase Order 呼叫 save()，觸發 before_save
    """
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
