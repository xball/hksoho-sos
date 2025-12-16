import frappe
from frappe.model.document import Document
import os
from datetime import datetime, date
from datetime import date, datetime, timedelta


# Constants
DEBUG_FILE = "/home/frappe/frappe-bench/temp/debug_log.txt"
OUTPUT_DIR = "/home/ftpuser/topyramid"
OUTPUT_DIR_OWN = "/home/frappe/topyramid"

LAST_NUMBER_FILE = "/home/frappe/last_number.txt"
INITIAL_SEQUENCE = 20000
FIELDS_TO_CHECK = ['po_status']
ITEM_FIELDS_TO_CHECK = ['article_number', 'line', 'article_name', 'unit_price', 'confirmed_qty', 'requested_qty', 'confirmed_shipdate']
LOGGER_NAME = "purchase_order_export"

def write_debug_log(message):
    """
    寫入除錯日誌到指定的 DEBUG_FILE。
    """
    try:
        os.makedirs(os.path.dirname(DEBUG_FILE), exist_ok=True)
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: {message}\n")
    except Exception as e:
        frappe.log_error(f"Failed to write debug log: {str(e)}")

class PurchaseOrder(Document):
    def before_validate(self):
        """
        在驗證前計算總確認數量、總確認金額、總預訂數量和總預訂金額。
        """
        logger = frappe.logger(LOGGER_NAME)
        try:
            write_debug_log(f"validate triggered for PO: {self.name}")
            logger.info(f"validate triggered for Purchase Order: {self.name}")
            treq_qty = 0
            treq_amt = 0.0
            tconf_qty = 0
            tconf_amt = 0.0
            tbook_qty = 0
            tbook_amt = 0.0
            for item in self.po_items:
                uprice = item.unit_price
                uconf_qty = item.confirmed_qty
                ubook_qty = item.booked_qty
                ureq_qty = item.requested_qty
                
                if uprice is None or uconf_qty is None:	
                    item.amount = 0.0
                else:
                    item.amount = uprice * uconf_qty
                    
                if uprice is None or ureq_qty is None:	
                    req_amt = 0.0
                else:
                    req_amt = uprice * ureq_qty

                treq_qty += ureq_qty or 0
                treq_amt += req_amt or 0.0

                tconf_qty += uconf_qty or 0
                tconf_amt += item.amount or 0.0
                tbook_qty += item.booked_qty or 0
                tbook_amt += uprice * ubook_qty if (uprice is not None and ubook_qty is not None) else 0.0

            self.total_confirmed_qty = tconf_qty
            self.total_confirmed_amount = tconf_amt
            self.total_booked_qty = tbook_qty
            self.total_booked_amount = tbook_amt
            self.total_requested_qty = treq_qty
            self.total_requested_amount = treq_amt            
            write_debug_log(f"##Purchase Order: {self.name} , req_QTY {self.total_requested_qty}")
        except Exception as e:
            frappe.log_error(f"Validate failed for PO: {self.name}, error: {str(e)}")
            write_debug_log(f"validate failed for PO: {self.name}, error: {str(e)}")

    def before_save(self):
        """
        在儲存前檢查是否需要匯出檔案，根據 sync_back_pyramid 和 latest_file_number 檔案內容決定是否生成新檔案。
        檔案名稱基於序號，帶有 'B' 前綴，從 20000 開始。
        將最新序號儲存至 last_number.txt。
        """
        logger = frappe.logger(LOGGER_NAME)
        logger.info(f"before_save triggered for Purchase Order: {self.name}")
        try:
            write_debug_log(f"before_save triggered for PO: {self.name}")
        except Exception as e:
            frappe.log_error(f"Before_save debug log write failed for PO: {self.name}, error: {str(e)}")
            write_debug_log(f"before_save debug log write failed for PO: {self.name}, error: {str(e)}")
            return

        # 檢查 sync_back_pyramid 欄位
        if (not self.get('sync_back_pyramid')) or self.workflow_state == "Draft":
            logger.info(f"sync_back_pyramid is False for PO: {self.name}, skipping export")
            write_debug_log(f"sync_back_pyramid is False for PO: {self.name}, skipping export")
            return

        # 開始構建檔案內容
        content = []
        try:
            partner_id = self.supplier
            po_id = self.name
            po_status = self.po_status
            content.append("01")
            content.append(f"#12205;{partner_id or ''}")
            content.append(f"#12203;{po_id}")
            content.append(f"#18780;{po_status.upper() or ''}")
            logger.info(f"Added header details for PO: {po_id}")
            write_debug_log(f"Added header details for PO: {po_id}")
        except Exception as e:
            logger.error(f"Failed to process header for PO: {po_id}: {str(e)}")
            frappe.log_error(f"Purchase Order header processing failed: {str(e)}")
            write_debug_log(f"Failed to process header for PO: {po_id}: {str(e)}")
            return

        # 處理採購訂單項目
        try:
            for item in self.po_items:
                if self.workflow_state == "Confirmed" and self.qc_requested:
                    item.qc_update_status = "On-going"
                    
                req_date = item.requested_shipdate 
                if req_date:
                    try:
                        date_obj = req_date if isinstance(req_date, date) else datetime.strptime(str(req_date), "%Y-%m-%d").date()
                        year = str(date_obj.year)[-2:]
                        week = str(date_obj.isocalendar()[1]).zfill(2)
                        req_date = f"{year}-{week}"
                        item.requested_shipdate_week = req_date
                    except ValueError as e:
                        logger.warning(f"Invalid requested_shipdate format for item {item.article_number}: {req_date}, error: {str(e)}")
                        write_debug_log(f"Invalid requested_shipdate format for item {item.article_number}: {req_date}, error: {str(e)}")
                        req_date = ''
                
                conf_date = item.confirmed_shipdate 
                if conf_date:
                    try:
                        date_obj = conf_date if isinstance(conf_date, date) else datetime.strptime(str(conf_date), "%Y-%m-%d").date()
                        year = str(date_obj.year)[-2:]
                        week = str(date_obj.isocalendar()[1]).zfill(2)
                        conf_date = f"{year}-{week}"
                        item.confirmed_ship_week = conf_date
                    except ValueError as e:
                        logger.warning(f"Invalid confirmed_shipdate format for item {item.article_number}: {conf_date}, error: {str(e)}")
                        write_debug_log(f"Invalid confirmed_shipdate format for item {item.article_number}: {conf_date}, error: {str(e)}")
                        conf_date = ''             
                           
                content.append("11")
                article_number = item.article_number or item.item_code or ''
                content.append(f"#12401;{article_number}")
                content.append(f"#12414;{item.line or ''}")
                content.append(f"#12421;{item.article_name or item.item_name or ''}")
                unit_price = item.unit_price or 0.0
                content.append(f"#12451;{unit_price}")
                logger.info(f"Item {article_number}: unit_price={unit_price}")
                write_debug_log(f"Item {article_number}: unit_price={unit_price}")
                
                
                # ---------- 關鍵修改：根據 order_status 決定 #12441 的值 ----------
                order_status = (item.order_status or "").strip()
                qc_status = (item.qc_update_status or "").strip()
                if qc_status and qc_status == "Pass":
                    qc_status_output = "APPROVED"
                else: 
                    qc_status_output = "REQUESTED"
                if order_status == "Shipped":
                # 已出貨 → 數量差異強制為 0
                    qty_diff = 0
                else:
                # 未出貨 → 原本邏輯：confirmed_qty - requested_qty
                    qty_diff = (item.remaining_qty or 0) 

                content.append(f"#12441;{qty_diff}")
                
                ship_date = item.confirmed_shipdate 
                if ship_date:
                    try:
                        date_obj = ship_date if isinstance(ship_date, date) else datetime.strptime(str(ship_date), "%Y-%m-%d").date()
                        date_obj = date_obj + timedelta(days=60)
                        year = str(date_obj.year)[-2:]
                        week = str(date_obj.isocalendar()[1]).zfill(2)
                        weekday = str(date_obj.isoweekday())
                        ship_date = f"{year}{week}{weekday}"
                    except ValueError as e:
                        logger.warning(f"Invalid confirmed_shipdate format for item {article_number}: {ship_date}, error: {str(e)}")
                        write_debug_log(f"Invalid confirmed_shipdate format for item {article_number}: {ship_date}, error: {str(e)}")
                        ship_date = ''
                
                content.append(f"¤5513;{ship_date or ''}")
                
                content.append(f"¤18549;{po_status.upper() or ''}")
                content.append(f"¤18550;{qc_status_output or ''}")
                
                if order_status == "Shipped":
                    # 新增 SHIPPED 標記
                    content.append(f"¤18551;SHIPPED")
                    # 新增 container_no（如有的話）
                    container_no = item.container_no or ""
                    content.append(f"¤18541;{container_no}")
            logger.info(f"Processed {len(self.po_items)} items for PO: {po_id}")
            write_debug_log(f"Processed {len(self.po_items)} items for PO: {po_id}")
        except Exception as e:
            logger.error(f"Failed to process PO items for {po_id}: {str(e)}")
            frappe.log_error(f"Purchase Order item processing failed: {str(e)}")
            write_debug_log(f"Failed to process PO items for {po_id}: {str(e)}")
            return

        # 將內容轉換為字串以進行比較
        new_content_str = "\n".join(content)

        # 檢查 latest_file_number 的檔案內容
        latest_file_number = self.get('latest_file_number') or ''
        if latest_file_number:
            try:
                latest_file_path = os.path.join(OUTPUT_DIR_OWN, f"{latest_file_number}.txt")
                if os.path.exists(latest_file_path):
                    with open(latest_file_path, "r", encoding="cp1252") as f:
                        existing_content = f.read()
                    if existing_content == new_content_str:
                        logger.info(f"Content for PO: {self.name} matches existing file {latest_file_number}, skipping export")
                        write_debug_log(f"Content for PO: {self.name} matches existing file {latest_file_number}, skipping export")
                        return
                    else:
                        logger.info(f"Content for PO: {self.name} differs from existing file {latest_file_number}, proceeding with export")
                        write_debug_log(f"Content for PO: {self.name} differs from existing file {latest_file_number}, proceeding with export")
                else:
                    logger.info(f"File {latest_file_path} does not exist, proceeding with export")
                    write_debug_log(f"File {latest_file_path} does not exist, proceeding with export")
            except Exception as e:
                logger.error(f"Failed to read file {latest_file_path}: {str(e)}")
                write_debug_log(f"Failed to read file {latest_file_path}: {str(e)}")
                return

        # 定義輸出目錄
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            write_debug_log(f"Created or verified directory: {OUTPUT_DIR}")
        except Exception as e:
            logger.error(f"Failed to create directory {OUTPUT_DIR}: {str(e)}")
            frappe.log_error(f"Purchase Order export directory creation failed: {str(e)}")
            write_debug_log(f"Failed to create directory {OUTPUT_DIR}: {str(e)}")
            return

        # 獲取下一個序號
        try:
            sequence = get_next_sequence_number()
            file_name = f"B{sequence}.txt"
            file_path = os.path.join(OUTPUT_DIR_OWN, file_name)
            file_path_ftp = os.path.join(OUTPUT_DIR, file_name)
            
            logger.info(f"Generating file: {file_path}")
            write_debug_log(f"Generating file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to get sequence number: {str(e)}")
            frappe.log_error(f"Purchase Order sequence number retrieval failed: {str(e)}")
            write_debug_log(f"Failed to get sequence number: {str(e)}")
            return

        # 更新 latest_file_number
        try:
            self.latest_file_number = f"B{sequence}"
            logger.info(f"Updated latest_file_number to B{sequence} for PO: {self.name}")
            write_debug_log(f"Updated latest_file_number to B{sequence} for PO: {self.name}")
        except Exception as e:
            logger.error(f"Failed to update latest_file_number for PO: {self.name}: {str(e)}")
            write_debug_log(f"Failed to update latest_file_number for PO: {self.name}: {str(e)}")
            return

        os.umask(0)
        # 寫入檔案內容
        try:
            with open(file_path, "w", encoding="cp1252") as f:
                f.write(new_content_str)
            with open(file_path_ftp, "w", encoding="cp1252") as f:
                f.write(new_content_str)
            logger.info(f"Successfully wrote file: {file_path}")
            write_debug_log(f"Successfully wrote file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {str(e)}")
            frappe.log_error(f"Purchase Order file write failed: {str(e)}")
            write_debug_log(f"Failed to write file {file_path}: {str(e)}")

    
    
    def after_save(self):
        """
        測試 after_save 事件是否被觸發。
        """
        logger = frappe.logger(LOGGER_NAME)
        try:
            frappe.msgprint(f"After_save triggered for PO: {self.name}")
            frappe.db.commit()
            write_debug_log(f"after_save triggered for PO: {self.name}")
            logger.info(f"after_save triggered for Purchase Order: {self.name}")
        except Exception as e:
            frappe.log_error(f"After_save failed for PO: {self.name}, error: {str(e)}")
            write_debug_log(f"after_save failed for PO: {self.name}, error: {str(e)}")

def get_next_sequence_number():
    """
    從 last_number.txt 獲取下一個序號，從 20000 開始。
    遞增並儲存新的序號。
    """
    logger = frappe.logger(LOGGER_NAME)
    sequence = INITIAL_SEQUENCE

    try:
        if os.path.exists(LAST_NUMBER_FILE):
            with open(LAST_NUMBER_FILE, "r", encoding="utf-8") as f:
                try:
                    sequence = int(f.read().strip()) + 1
                    logger.info(f"Read sequence number: {sequence - 1}, incremented to: {sequence}")
                    write_debug_log(f"Read sequence number: {sequence - 1}, incremented to: {sequence}")
                except ValueError:
                    sequence = INITIAL_SEQUENCE
                    logger.warning(f"Invalid content in {LAST_NUMBER_FILE}, using default sequence: {sequence}")
                    write_debug_log(f"Invalid content in {LAST_NUMBER_FILE}, using default sequence: {sequence}")
        else:
            logger.info(f"No {LAST_NUMBER_FILE} found, using default sequence: {sequence}")
            write_debug_log(f"No {LAST_NUMBER_FILE} found, using default sequence: {sequence}")
    except Exception as e:
        logger.error(f"Failed to read {LAST_NUMBER_FILE}: {str(e)}")
        frappe.log_error(f"Sequence number read failed: {str(e)}")
        write_debug_log(f"Failed to read {LAST_NUMBER_FILE}: {str(e)}")
        return sequence

    try:
        with open(LAST_NUMBER_FILE, "w", encoding="utf-8") as f:
            f.write(str(sequence))
        logger.info(f"Saved new sequence number: {sequence} to {LAST_NUMBER_FILE}")
        write_debug_log(f"Saved new sequence number: {sequence} to {LAST_NUMBER_FILE}")
    except Exception as e:
        logger.error(f"Failed to write {LAST_NUMBER_FILE}: {str(e)}")
        frappe.log_error(f"Sequence number write failed: {str(e)}")
        write_debug_log(f"Failed to write {LAST_NUMBER_FILE}: {str(e)}")

    return sequence