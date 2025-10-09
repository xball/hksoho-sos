import frappe
from frappe import _
import json

@frappe.whitelist()
def link_attachments_to_products(file_docs, products):
    try:
        # 驗證 products（不能為空或非列表）
        if not products or not isinstance(products, list) or len(products) == 0:
            frappe.throw(_('無產品列表或格式錯誤，檔案必須關聯至少一個產品'))

        # 驗證 file_docs
        if not file_docs:
            frappe.throw(_('無檔案資料傳入'))

        # 除錯：記錄原始 file_docs
        frappe.log_error(f"Raw file_docs type: {type(file_docs)}, value: {file_docs}", "Product Attachment Debug")

        # 如果 file_docs 是字串，解析為列表
        if isinstance(file_docs, str):
            try:
                file_docs = json.loads(file_docs)
            except json.JSONDecodeError:
                frappe.throw(_('file_docs 字串解析失敗：無效的 JSON 格式：{}').format(file_docs))

        if not isinstance(file_docs, list):
            file_docs = [file_docs]

        # 除錯：記錄解析後的 file_docs
        frappe.log_error(f"Parsed file_docs: {file_docs}", "Product Attachment Debug")

        # 記錄輸入
        frappe.log_error(f"Received {len(file_docs)} files and {len(products)} products", "Product Attachment Debug")

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
                # "file_type": file_doc.get('file_type') or "Other",
                "file_type": "Image",
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
        frappe.log_error(frappe.get_traceback(), 'Product Attachment Upload Error')
        frappe.throw(_('上傳過程出錯：{}').format(str(e)))