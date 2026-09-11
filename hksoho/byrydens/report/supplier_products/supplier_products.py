import frappe

def execute(filters=None):
    user = frappe.session.user
    
    columns = [
        {
            "fieldname": "article_number",
            "label": "Article Number",
            "fieldtype": "Link",
            "options": "Product",
            "width": 150
        },
        {
            "fieldname": "article_name",
            "label": "Article Name",
            "fieldtype": "Data",
            "width": 250
        },
        {
            "fieldname": "category",
            "label": "Category",
            "fieldtype": "Link",
            "options": "Product Group",
            "width": 150
        },
        {
            "fieldname": "supplier",
            "label": "Supplier",
            "fieldtype": "Link",
            "options": "Partner",
            "width": 180
        },
    ]
    
    # ====================== 只檢查 User Permission ======================
    permissions = frappe.get_all(
        "User Permission",
        filters={
            "user": user,
            "allow": "Partner"
        },
        fields=["for_value"]
    )
    
    # 自動去除重複 + 過濾空值（支援多個權限）
    allowed_suppliers = list({p.for_value for p in permissions if p.for_value})
    
    if not allowed_suppliers:
        # 沒有設定任何 Partner 權限 → 顯示全部 Product
        data = frappe.db.sql("""
            SELECT 
                p.article_number,
                p.article_name,
                p.category,
                p.supplier
            FROM `tabProduct` p
            ORDER BY p.article_number
        """, as_dict=True)
    else:
        # 有 Partner 權限 → 只顯示 supplier 在允許清單內的 Product
        data = frappe.db.sql("""
            SELECT 
                p.article_number,
                p.article_name,
                p.category,
                p.supplier
            FROM `tabProduct` p
            WHERE p.supplier IN %(suppliers)s
            ORDER BY p.article_number
        """, {"suppliers": allowed_suppliers}, as_dict=True)
    
    return columns, data