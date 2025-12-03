import frappe
from frappe import _

def execute(filters=None):
    # 使用您系統真正的欄位：requested_qty
    data = frappe.db.sql("""
        SELECT 
            YEAR(po.po_shipdate) AS year,
            MONTH(po.po_shipdate) AS month_num,
            SUM((item.requested_qty - COALESCE(item.booked_qty, 0)) * item.unit_price) AS due_amount
        FROM `tabPurchase Order` po
        JOIN `tabPurchase Order Item` item ON item.parent = po.name
        WHERE po.po_shipdate IS NOT NULL
          AND item.requested_qty > COALESCE(item.booked_qty, 0)
          AND item.requested_qty > 0
          AND item.unit_price > 0
        GROUP BY YEAR(po.po_shipdate), MONTH(po.po_shipdate)
        HAVING due_amount > 0
        ORDER BY year ASC, month_num ASC
    """, as_dict=1)

    if not data:
        return [
            {"label": "訊息", "fieldname": "msg", "fieldtype": "Data", "width": 600}
        ], [{"msg": "目前沒有任何未出貨訂單（requested_qty > booked_qty）"}]

    rows = []
    total = 0

    for d in data:
        month_name = frappe.utils.getdate(f"{d.year}-{d.month_num:02d}-01").strftime("%B %Y")
        rows.append({
            "year": d.year,
            "month": month_name,
            "due_amount": d.due_amount,
            "details": {"label": "View Details"}
        })
        total += float(d.due_amount)

    # 總計列
    rows.append({
        "year": "",
        "month": "<strong style='color:#e74c3c; font-size:16px;'>Grand Total (All Time)</strong>",
        "due_amount": total,
        "details": ""
    })

    columns = [
        {"label": "Year",       "fieldname": "year",       "fieldtype": "Int",      "width": 80},
        {"label": "Month",      "fieldname": "month",      "fieldtype": "Data",     "width": 160},
        {"label": "Amount Due", "fieldname": "due_amount", "fieldtype": "Currency", "width": 180},
        {"label": "Details",    "fieldname": "details",    "fieldtype": "Button",   "width": 130}
    ]

    return columns, rows