# Copyright (c) 2025, HKSoHo and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    # 定義要顯示的年份範圍
    current_year = int(frappe.utils.nowdate()[:4])
    start_year = 2023  # 起始年份
    end_year = current_year + 2  # 顯示到未來2年

    columns = [
        {"label": _("Year"), "fieldname": "year", "fieldtype": "Data", "width": 80},
        {"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 110},
        {"label": _("Amount Due"), "fieldname": "due_amount", "fieldtype": "Currency", "width": 160},
        {"label": _("Details"), "fieldname": "details", "fieldtype": "Button", "width": 110},
    ]

    month_names = {1:"January", 2:"February", 3:"March", 4:"April", 5:"May", 6:"June",
                   7:"July", 8:"August", 9:"September", 10:"October", 11:"November", 12:"December"}

    data = []
    grand_total = 0

    # 循環每一年
    for year in range(start_year, end_year + 1):
        yearly_total = 0
        currency_summary = {}
        year_has_data = False

        # 循環每個月
        for m in range(1, 13):
            start = f"{year}-{str(m).zfill(2)}-01"
            end = frappe.utils.get_last_day(start)

            result = frappe.db.sql("""
                SELECT po.order_purchase_currency,
                       SUM(item.confirmed_qty * item.unit_price) AS amt
                FROM `tabPurchase Order` po
                JOIN `tabPurchase Order Item` item ON item.parent = po.name
                WHERE 
                  po.po_shipdate BETWEEN %s AND %s
                  AND COALESCE(item.order_status, '') != "Shipped"
                GROUP BY po.order_purchase_currency
            """, (start, end), as_dict=1)

            month_total = sum(frappe.utils.flt(r.amt or 0) for r in result)
            
            for r in result:
                currency_summary[r.order_purchase_currency] = currency_summary.get(r.order_purchase_currency, 0) + frappe.utils.flt(r.amt or 0)

            yearly_total += month_total

            # 只加入 due_amount > 0 的資料行
            if month_total > 0:
                year_has_data = True
                data.append({
                    "year": year,
                    "month": month_names[m],
                    "due_amount": month_total,
                    "details": {"label": "View Details"}
                })

        # 加入年度小計（只在該年有資料時）
        if year_has_data and yearly_total > 0:
            breakdown = "<br>".join([f"{c}: {a:,.2f}" for c, a in currency_summary.items()])
            data.append({
                "year": year,
                "month": f"<strong style='color:#2980b9;'>Sub-Total {year}</strong>",
                "due_amount": yearly_total,
                "details": ""
            })
            grand_total += yearly_total

    # 加入總計行
    if grand_total > 0:
        data.append({
            "year": "",
            "month": f"<strong style='color:#e74c3c;'>Grand Total ({start_year}-{end_year})</strong>",
            "due_amount": grand_total,
            "details": ""
        })

    return columns, data
