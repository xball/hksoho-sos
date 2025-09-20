import frappe
from frappe.model.document import Document
import os
from datetime import datetime, date

# Constants
DEBUG_FILE = "/home/frappe/frappe-bench/temp/debug_log.txt"
OUTPUT_DIR = "/home/ftpuser/topyramid"
LAST_NUMBER_FILE = "/home/ftpuser/topyramid/last_number.txt"
INITIAL_SEQUENCE = 20000
FIELDS_TO_CHECK = ['po_status']
ITEM_FIELDS_TO_CHECK = ['article_number', 'line', 'article_name', 'unit_price', 'confirmed_qty', 'requested_qty', 'confirmed_shipdate']
LOGGER_NAME = "purchase_order_export"

class PurchaseOrder(Document):
    def before_validate(self):
        """
        Test if validate event is triggered.
        """
        logger = frappe.logger(LOGGER_NAME)
        try:
            os.makedirs(os.path.dirname(DEBUG_FILE), exist_ok=True)
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: validate triggered for PO: {self.name}\n")
            logger.info(f"validate triggered for Purchase Order: {self.name}")
            tconf_qty = 0
            tconf_amt = 0.0
            tbook_qty = 0
            tbook_amt = 0.0
            for item in self.po_items:
                uprice = item.unit_price
                uconf_qty = item.confirmed_qty
                ubook_qty = item.booked_qty
                if uprice is None or uconf_qty is None:	
                    item.amount = 0.0
                else:
                    item.amount = uprice * uconf_qty
                tconf_qty += uconf_qty or 0
                tconf_amt += item.amount or 0.0
                tbook_qty += item.booked_qty or 0
                tbook_amt += uprice * ubook_qty if (uprice is not None and ubook_qty is not None) else 0.0

            self.total_confirmed_qty = tconf_qty
            self.total_confirmed_amount = tconf_amt
            self.total_booked_qty = tbook_qty
            self.total_booked_amount = tbook_amt
            
            
        except Exception as e:
            frappe.log_error(f"Validate failed for PO: {self.name}, error: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: validate failed for PO: {self.name}, error: {str(e)}\n")

    def before_save(self):
        """
        Export specific fields to a txt file when specific fields in a Purchase Order are modified.
        File name is based on a sequence number with prefix 'B', starting from 20000.
        Stores the last sequence number in last_number.txt.
        """
        logger = frappe.logger(LOGGER_NAME)
        logger.info(f"before_save triggered for Purchase Order: {self.name}")
        try:
            os.makedirs(os.path.dirname(DEBUG_FILE), exist_ok=True)
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: before_save triggered for PO: {self.name}\n")
        except Exception as e:
            frappe.log_error(f"Before_save debug log write failed for PO: {self.name}, error: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: before_save debug log write failed for PO: {self.name}, error: {str(e)}\n")
            return

        # Check if relevant fields have changed
        has_changes = False
        previous_doc = self.get_doc_before_save()

        if previous_doc:
            # Check main document fields
            for field in FIELDS_TO_CHECK:
                current_value = self.get(field) or ''
                previous_value = previous_doc.get(field) or ''
                if current_value != previous_value:
                    has_changes = True
                    logger.info(f"Field {field} changed from {previous_value} to {current_value}")
                    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now()}: Field {field} changed from {previous_value} to {current_value}\n")
                    break

            # Check po_items changes
            if not has_changes:
                current_items = [
                    tuple(item.get(field) or '' for field in ITEM_FIELDS_TO_CHECK)
                    for item in self.po_items
                ]
                previous_items = [
                    tuple(item.get(field) or '' for field in ITEM_FIELDS_TO_CHECK)
                    for item in previous_doc.po_items
                ]
                if current_items != previous_items or len(self.po_items) != len(previous_doc.po_items):
                    has_changes = True
                    logger.info(f"po_items changed")
                    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now()}: po_items changed\n")
        else:
            # New document or no previous state, treat as changed
            has_changes = True
            logger.info(f"New Purchase Order or no previous state, triggering export")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: New Purchase Order or no previous state, triggering export\n")

        if not has_changes:
            logger.info(f"No relevant changes detected for PO: {self.name}, skipping export")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: No relevant changes detected for PO: {self.name}, skipping export\n")
            return

        # Define the output directory
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Created or verified directory: {OUTPUT_DIR}\n")
        except Exception as e:
            logger.error(f"Failed to create directory {OUTPUT_DIR}: {str(e)}")
            frappe.log_error(f"Purchase Order export directory creation failed: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Failed to create directory {OUTPUT_DIR}: {str(e)}\n")
            return

        # Get the next sequence number
        try:
            sequence = get_next_sequence_number()
            file_name = f"B{sequence}.txt"
            file_path = os.path.join(OUTPUT_DIR, file_name)
            logger.info(f"Generating file: {file_path}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Generating file: {file_path}\n")
        except Exception as e:
            logger.error(f"Failed to get sequence number: {str(e)}")
            frappe.log_error(f"Purchase Order sequence number retrieval failed: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Failed to get sequence number: {str(e)}\n")
            return

        # Start building the file content
        content = []

        # Hardcoded line '01' and header details
        try:
            partner_id = self.supplier  # Assuming supplier field links to Partner doctype
            po_id = self.name
            po_status = self.po_status  # Assuming po_status is a field in Purchase Order
            content.append("01")
            content.append(f"#12205;{partner_id or ''}")
            content.append(f"#12203;{po_id}")
            content.append(f"#18780;{po_status.upper() or ''}")
            logger.info(f"Added header details for PO: {po_id}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Added header details for PO: {po_id}\n")
        except Exception as e:
            logger.error(f"Failed to process header for PO: {po_id}: {str(e)}")
            frappe.log_error(f"Purchase Order header processing failed: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Failed to process header for PO: {po_id}: {str(e)}\n")
            return

        # Process PO items
        try:
            for item in self.po_items:
                
          	    # if self.workflow_state == "Ready to QC" and self.qc_required:
                if self.workflow_state == "Confirmed" and self.qc_requested:
                    item.qc_update_status = "On-going"
                    
                req_date = item.requested_shipdate 
                if req_date:
                    try:
                        # Convert date to YYWWN format (e.g., 2026-02-12 -> 26074)
                        date_obj = ship_date if isinstance(req_date, date) else datetime.strptime(str(req_date), "%Y-%m-%d").date()
                        year = str(date_obj.year) # Last 2 digits of year
                        week = date_obj.isocalendar()[1]
                        req_date = f"{year}-{week}"
                        item.requested_shipdate_week = req_date
                    except ValueError as e:
                        logger.warning(f"Invalid confirmed_shipdate format for item {article_number}: {req_date}, error: {str(e)}")
                        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                            f.write(f"{datetime.now()}: Invalid confirmed_shipdate format for item {article_number}: {req_date}, error: {str(e)}\n")
                        req_date = ''
                
                req_date = item.confirmed_shipdate 
                if req_date:
                    try:
                        # Convert date to YYWWN format (e.g., 2026-02-12 -> 26074)
                        date_obj = ship_date if isinstance(req_date, date) else datetime.strptime(str(req_date), "%Y-%m-%d").date()
                        year = str(date_obj.year) # Last 2 digits of year
                        week = date_obj.isocalendar()[1]
                        req_date = f"{year}-{week}"
                        item.confirmed_ship_week = req_date
                    except ValueError as e:
                        logger.warning(f"Invalid confirmed_shipdate format for item {article_number}: {req_date}, error: {str(e)}")
                        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                            f.write(f"{datetime.now()}: Invalid confirmed_shipdate format for item {article_number}: {req_date}, error: {str(e)}\n")
                        req_date = ''             
                           
                content.append("11")
                article_number = item.article_number or item.item_code or ''
                content.append(f"#12401;{article_number}")
                content.append(f"#12414;{item.line or  '' }")
                content.append(f"#12421;{item.article_name or item.item_name or ''}")
                unit_price = item.unit_price or 0.0  # Use unit_price only
                content.append(f"#12451;{unit_price}")
                logger.info(f"Item {article_number}: unit_price={unit_price}")
                with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now()}: Item {article_number}: unit_price={unit_price}\n")
                qty_diff = (item.confirmed_qty ) - (item.requested_qty )
                content.append(f"#12441;{qty_diff}")
                ship_date = item.confirmed_shipdate 
                if ship_date:
                    try:
                        # Convert date to YYWWN format (e.g., 2026-02-12 -> 26074)
                        date_obj = ship_date if isinstance(ship_date, date) else datetime.strptime(str(ship_date), "%Y-%m-%d").date()
                        year = str(date_obj.year)[-2:]  # Last 2 digits of year
                        week = str(date_obj.isocalendar()[1]).zfill(2)  # Week number, padded to 2 digits
                        weekday = str(date_obj.isoweekday())  # 1=Monday, 4=Thursday
                        ship_date = f"{year}{week}{weekday}"
                    except ValueError as e:
                        logger.warning(f"Invalid confirmed_shipdate format for item {article_number}: {ship_date}, error: {str(e)}")
                        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                            f.write(f"{datetime.now()}: Invalid confirmed_shipdate format for item {article_number}: {ship_date}, error: {str(e)}\n")
                        ship_date = ''
                content.append(f"#5513;{ship_date or ''} ")
            logger.info(f"Processed {len(self.po_items)} items for PO: {po_id}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Processed {len(self.po_items)} items for PO: {po_id}\n")
                
                

        except Exception as e:
            logger.error(f"Failed to process PO items for {po_id}: {str(e)}")
            frappe.log_error(f"Purchase Order item processing failed: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Failed to process PO items for {po_id}: {str(e)}\n")
            return

        # Write content to file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(content))
            logger.info(f"Successfully wrote file: {file_path}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Successfully wrote file: {file_path}\n")
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {str(e)}")
            frappe.log_error(f"Purchase Order file write failed: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: Failed to write file {file_path}: {str(e)}\n")

    def after_save(self):
        """
        Test if after_save event is triggered.
        """
        logger = frappe.logger(LOGGER_NAME)
        try:
            frappe.msgprint(f"After_save triggered for PO: {self.name}")
            frappe.db.commit()
            os.makedirs(os.path.dirname(DEBUG_FILE), exist_ok=True)
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: after_save triggered for PO: {self.name}\n")
            logger.info(f"after_save triggered for Purchase Order: {self.name}")
        except Exception as e:
            frappe.log_error(f"After_save failed for PO: {self.name}, error: {str(e)}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: after_save failed for PO: {self.name}, error: {str(e)}\n")

def get_next_sequence_number():
    """
    Get the next sequence number from last_number.txt, starting from 20000.
    Increment and save the new sequence number.
    """
    logger = frappe.logger(LOGGER_NAME)
    sequence = INITIAL_SEQUENCE

    try:
        if os.path.exists(LAST_NUMBER_FILE):
            with open(LAST_NUMBER_FILE, "r", encoding="utf-8") as f:
                try:
                    sequence = int(f.read().strip()) + 1
                    logger.info(f"Read sequence number: {sequence - 1}, incremented to: {sequence}")
                    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now()}: Read sequence number: {sequence - 1}, incremented to: {sequence}\n")
                except ValueError:
                    sequence = INITIAL_SEQUENCE
                    logger.warning(f"Invalid content in {LAST_NUMBER_FILE}, using default sequence: {sequence}")
                    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now()}: Invalid content in {LAST_NUMBER_FILE}, using default sequence: {sequence}\n")
        else:
            logger.info(f"No {LAST_NUMBER_FILE} found, using default sequence: {sequence}")
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: No {LAST_NUMBER_FILE} found, using default sequence: {sequence}\n")
    except Exception as e:
        logger.error(f"Failed to read {LAST_NUMBER_FILE}: {str(e)}")
        frappe.log_error(f"Sequence number read failed: {str(e)}")
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: Failed to read {LAST_NUMBER_FILE}: {str(e)}\n")
        return sequence

    try:
        with open(LAST_NUMBER_FILE, "w", encoding="utf-8") as f:
            f.write(str(sequence))
        logger.info(f"Saved new sequence number: {sequence} to {LAST_NUMBER_FILE}")
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: Saved new sequence number: {sequence} to {LAST_NUMBER_FILE}\n")
    except Exception as e:
        logger.error(f"Failed to write {LAST_NUMBER_FILE}: {str(e)}")
        frappe.log_error(f"Sequence number write failed: {str(e)}")
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: Failed to write {LAST_NUMBER_FILE}: {str(e)}\n")

    return sequence