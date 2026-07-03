import frappe
from frappe import _

@frappe.whitelist()
def get_product_attachments(product_name):
    try:
        # Debug: Log input
        frappe.log_error(message=f"Fetching attachments for product: {product_name}", title="Product Attachment Debug")

        # Check user permission
        has_permission = frappe.has_permission('Product Attachment Link', 'read')
        frappe.log_error(message=f"User permission for Product Attachment Link: {has_permission}", title="Product Attachment Debug")

        # Fetch associated attachment links
        links = frappe.get_all('Product Attachment Link', 
                              filters={'product': product_name},
                              fields=['parent'])
        frappe.log_error(message=f"Found {len(links)} links", title="Product Attachment Debug")

        if not links:
            return {'html': '<p>No associated attachments</p>'}

        attachment_names = [link['parent'] for link in links]
        frappe.log_error(message=f"Attachment Names: {attachment_names}", title="Product Attachment Debug")

        # Validate attachment names
        valid_attachments = frappe.get_all('Product Attachment',
                                          filters={'name': ['in', attachment_names],'active': 1},
                                          fields=['name'])
        valid_names = [att['name'] for att in valid_attachments]
        frappe.log_error(message=f"Valid Attachment Names: {valid_names}", title="Product Attachment Debug")

        # Fetch attachment details for valid names only
        attachments = frappe.get_all('Product Attachment',
                                   filters={'name': ['in', valid_names],'active': 1},
                                   fields=['name', 'attachment_name', 'file_type', 'attachment_file'])
        frappe.log_error(message=f"Found {len(attachments)} attachments", title="Product Attachment Debug")

        # Generate HTML table
        html = '<table class="table table-bordered">'
        html += '<thead><tr><th>File Name</th><th>Type</th><th>Download</th></tr></thead>'
        html += '<tbody>'
        for attachment in attachments:
            attachment_url = f'/app/product-attachment/{attachment["name"]}'
            html += f'<tr><td><a href="{attachment_url}" target="_blank">{attachment.attachment_name}</a></td><td>{attachment.file_type}</td><td><a href="{attachment.attachment_file}" target="_blank">Download</a></td></tr>'
        
        html += '</tbody></table>'

        return {'html': html}

    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="Product Attachment Error")
        return {'html': '<p>Error loading attachments</p>'}

@frappe.whitelist()
def link_attachments_to_products(file_docs, products):
    try:
        # 驗證 file_docs
        if not file_docs:
            frappe.throw(_('無檔案資料傳入'))

        if isinstance(file_docs, str):
            frappe.throw(_('file_docs 格式錯誤，應為物件列表而非字串：{}').format(file_docs))
        if not isinstance(file_docs, list):
            file_docs = [file_docs]

        # 驗證 products（不能為空或非列表）
        if not products or not isinstance(products, list) or len(products) == 0:
            frappe.throw(_('無產品列表或格式錯誤，檔案必須關聯至少一個產品'))

        # 除錯：記錄輸入（短 title，長 message）
        frappe.log_error("Product Attachment Debug", f"Received {len(file_docs)} files and {len(products)} products. Raw file_docs: {file_docs}")

        for file_doc in file_docs:
            # 驗證 file_doc 是字典
            if not isinstance(file_doc, dict):
                frappe.throw(_('無效的 file_doc 格式：{}').format(str(file_doc)))

            # 檢查必要欄位
            if not file_doc.get('file_url'):
                frappe.throw(_('檔案缺少 file_url：{}').format(file_doc.get('file_name', '未知')))
            if not file_doc.get('file_name'):
                file_doc['file_name'] = 'Unknown'

            # 檢查檔案是否在 File DocType 中
            if not frappe.db.exists('File', {'file_url': file_doc.get('file_url')}):
                frappe.throw(_('檔案未在 File DocType 中找到：{}').format(file_doc.get('file_url')))

            # 創建 Product Attachment
            attachment_doc = frappe.get_doc({
                "doctype": "Product Attachment",
                "attachment_name": file_doc.get('file_name'),
                "attachment_file": file_doc.get('file_url'),
                "file_type": "Other",
                "description": "",
                "uploaded_by": frappe.session.user,
                "upload_date": frappe.utils.nowdate()
            })
            attachment_doc.insert(ignore_permissions=True)

            # 關聯產品
            for product in products:
                if not frappe.db.exists("Product", product):
                    frappe.throw(_('產品 {} 不存在').format(product))
                product_doc = frappe.get_doc("Product", product)
                product_doc.append("attachments", {
                    "product": product,
                    "attachment": attachment_doc.name,
                    "is_primary": 0
                })
                product_doc.save(ignore_permissions=True)

        frappe.db.commit()
        return {
            'status': 'success',
            'message': _('成功處理 {} 個檔案，關聯到 {} 個產品').format(len(file_docs), len(products))
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error('Product Attachment Upload Error', frappe.get_traceback())
        frappe.throw(_('上傳過程出錯：{}').format(str(e)))
        

@frappe.whitelist()
def get_po_items_for_product(article_number):
    """
    取得指定 article_number 的所有 Purchase Order Items
    以及對應的 PO header 資料
    """
    if not article_number:
        return []

    # Query Purchase Order Items
    items = frappe.db.sql("""
        SELECT 
            poi.name,
            poi.po_number,
            poi.line,
            poi.article_name,
            poi.confirmed_qty,
            poi.booked_qty,
            poi.unit_price,
            poi.amount,
            poi.requested_shipdate,
            poi.confirmed_shipdate,
            po.order_type,
            po.supplier,
            po.po_placed,
            po.po_status,
            po.qc_status
        FROM `tabPurchase Order Item` poi
        LEFT JOIN `tabPurchase Order` po ON poi.po_number = po.po_number
        WHERE poi.article_number = %(article_number)s
        ORDER BY poi.po_number DESC, poi.line ASC
    """, {"article_number": article_number}, as_dict=True)

    return items



@frappe.whitelist()
def get_purchase_order_items_for_product(article_number):
    """
    取得 Purchase Order Items（現有系統）
    """
    if not article_number:
        return []

    items = frappe.db.sql("""
        SELECT 
            poi.name,
            poi.po_number,
            poi.line,
            poi.confirmed_qty,
            poi.booked_qty,
            poi.unit_price,
            poi.amount,
            poi.requested_shipdate,
            poi.confirmed_shipdate,
            po.order_type,
            po.supplier,
            po.po_placed,
            po.po_status,
            po.qc_status
        FROM `tabPurchase Order Item` poi
        LEFT JOIN `tabPurchase Order` po ON poi.po_number = po.po_number
        WHERE poi.article_number = %(article_number)s
        ORDER BY poi.po_number DESC, poi.line ASC
    """, {"article_number": article_number}, as_dict=True)

    return items


@frappe.whitelist()
def get_xpin_po_items_for_product(article_number):
    """
    取得 xpin_po_items（舊系統匯入）
    """
    if not article_number:
        return []

    items = frappe.db.sql("""
        SELECT 
            poi.name,
            poi.po_number,
            poi.line,
            poi.article_name,
            poi.requested_ship_week,
            poi.requested_qty,
            poi.confirmed_ship_week,
            poi.confirmed_qty,
            poi.booked_qty,
            poi.delivery_qty,
            poi.unit_price,
            poi.amount,
            po.supplier,
            po.buyer,
            po.order_placed,
            po.finish_date,
            po.po_status,
            po.qc_status
        FROM `tabxpin_po_items` poi
        LEFT JOIN `tabxpin_po` po ON poi.po_number = po.po_number
        WHERE poi.art_nr = %(article_number)s
        ORDER BY poi.po_number DESC, poi.line ASC
    """, {"article_number": article_number}, as_dict=True)

    return items
