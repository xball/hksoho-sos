import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    # 安全處理 filters，避免 KeyError
    etd_date_from = filters.get("etd_date_from")
    workflow_state = filters.get("workflow_state")

    query = """
		SELECT
            tor.name AS `TO Name:Data:150`,
            tor.etd_date AS `ETD Date:Date:110`,
            tor.workflow_state AS `Status:Data:120`,
            COUNT(*) AS `Count:Int:80`
        FROM `tabTransport Order` tor
        WHERE tor.mode = 'Sea'
        GROUP BY tor.name, tor.etd_date, tor.workflow_state
        LIMIT 50
    """

    data = frappe.db.sql(query, as_dict=True)

    columns = [
        {"label": "PO Number", "fieldname": "po_number", "width": 130},
        {"label": "Supplier", "fieldname": "supplier", "width": 200},
        {"label": "Group", "fieldname": "group", "width": 100},
        {"label": "Dest Port", "fieldname": "dest_port", "width": 100},
        {"label": "Vessel", "fieldname": "vessel", "width": 150},
        {"label": "Container", "fieldname": "container", "width": 120},
        {"label": "Size", "fieldname": "size", "width": 80},
        {"label": "Ship Date", "fieldname": "ship_date", "fieldtype": "Date", "width": 110},
        {"label": "ETA Date", "fieldname": "eta_date", "fieldtype": "Date", "width": 110},
        {"label": "Value On Water", "fieldname": "value_on_water", "fieldtype": "Currency", "width": 130},
        {"label": "Exchange Rate to SEK", "fieldname": "exchange_rate_to_sek", "fieldtype": "Float", "width": 130},
        {"label": "Value in SEK", "fieldname": "value_in_sek", "fieldtype": "Currency", "width": 140},
        {"label": "Currency", "fieldname": "currency", "width": 90},
        {"label": "Dvy Status", "fieldname": "dvy_status", "width": 100},
        {"label": "Customer", "fieldname": "customer", "width": 180},
        {"label": "DC", "fieldname": "dc", "width": 80},
        {"label": "Invoice#", "fieldname": "invoice_no", "width": 120},
        {"label": "Status", "fieldname": "status", "width": 100},
    ]

    return columns, data