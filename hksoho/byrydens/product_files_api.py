import frappe
from frappe import _


@frappe.whitelist()
def get_product_attachments(product_name):
    try:
        if not frappe.has_permission("Product", "read", product_name):
            frappe.throw(_("You do not have permission to read this product."), frappe.PermissionError)

        links = frappe.get_all(
            "Product Attachment Link",
            filters={"product": product_name},
            fields=["parent"],
        )

        if not links:
            return {"html": "<p>No associated attachments</p>"}

        attachment_names = [link["parent"] for link in links]

        valid_attachments = frappe.get_all(
            "Product Attachment",
            filters={"name": ["in", attachment_names], "active": 1},
            fields=["name"],
        )
        valid_names = [att["name"] for att in valid_attachments]

        attachments = frappe.get_all(
            "Product Attachment",
            filters={"name": ["in", valid_names], "active": 1},
            fields=["name", "attachment_name", "file_type", "attachment_file"],
        )

        html = '<table class="table table-bordered">'
        html += "<thead><tr><th>File Name</th><th>Type</th><th>Download</th></tr></thead>"
        html += "<tbody>"
        for attachment in attachments:
            attachment_url = f'/app/product-attachment/{attachment["name"]}'
            html += (
                f'<tr><td><a href="{attachment_url}" target="_blank">{attachment.attachment_name}</a></td>'
                f"<td>{attachment.file_type}</td>"
                f'<td><a href="{attachment.attachment_file}" target="_blank">Download</a></td></tr>'
            )

        html += "</tbody></table>"

        return {"html": html}

    except Exception:
        frappe.log_error(message=frappe.get_traceback(), title="Product Attachment Error")
        return {"html": "<p>Error loading attachments</p>"}


@frappe.whitelist()
def link_attachments_to_products(file_docs, products):
    try:
        if not file_docs:
            frappe.throw(_("No file data provided"))

        if isinstance(file_docs, str):
            frappe.throw(_("Invalid file_docs format: expected a list, got string"))
        if not isinstance(file_docs, list):
            file_docs = [file_docs]

        if not products or not isinstance(products, list) or len(products) == 0:
            frappe.throw(_("Products list is missing or invalid; files must be linked to at least one product"))

        for product in products:
            if not frappe.has_permission("Product", "write", product):
                frappe.throw(_("You do not have permission to update product {0}").format(product), frappe.PermissionError)

        for file_doc in file_docs:
            if not isinstance(file_doc, dict):
                frappe.throw(_("Invalid file_doc format: {0}").format(str(file_doc)))

            if not file_doc.get("file_url"):
                frappe.throw(_("File missing file_url: {0}").format(file_doc.get("file_name", "unknown")))
            if not file_doc.get("file_name"):
                file_doc["file_name"] = "Unknown"

            if not frappe.db.exists("File", {"file_url": file_doc.get("file_url")}):
                frappe.throw(_("File not found in File DocType: {0}").format(file_doc.get("file_url")))

            attachment_doc = frappe.get_doc({
                "doctype": "Product Attachment",
                "attachment_name": file_doc.get("file_name"),
                "attachment_file": file_doc.get("file_url"),
                "file_type": "Other",
                "description": "",
                "uploaded_by": frappe.session.user,
                "upload_date": frappe.utils.nowdate(),
            })
            attachment_doc.insert()

            for product in products:
                if not frappe.db.exists("Product", product):
                    frappe.throw(_("Product {0} does not exist").format(product))
                product_doc = frappe.get_doc("Product", product)
                product_doc.append("attachments", {
                    "product": product,
                    "attachment": attachment_doc.name,
                    "is_primary": 0,
                })
                product_doc.save()

        return {
            "status": "success",
            "message": _("Successfully processed {0} files for {1} products").format(len(file_docs), len(products)),
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Product Attachment Upload Error", frappe.get_traceback())
        frappe.throw(_("Upload failed: {0}").format(str(e)))


@frappe.whitelist()
def get_po_items_for_product(article_number):
    """Return Purchase Order Items and header data for an article number."""
    if not article_number:
        return []

    if not frappe.has_permission("Purchase Order", "read"):
        frappe.throw(_("You do not have permission to read Purchase Orders."), frappe.PermissionError)

    return frappe.db.sql("""
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


@frappe.whitelist()
def get_purchase_order_items_for_product(article_number):
    """Backward-compatible alias for get_po_items_for_product."""
    return get_po_items_for_product(article_number)


@frappe.whitelist()
def get_xpin_po_items_for_product(article_number):
    """Return legacy xpin_po_items for an article number."""
    if not article_number:
        return []

    if not frappe.has_permission("xpin_po", "read"):
        frappe.throw(_("You do not have permission to read legacy PO data."), frappe.PermissionError)

    return frappe.db.sql("""
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
