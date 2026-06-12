frappe.query_reports["Shipment On Water Report"] = {
    "filters": [
        {
            "fieldname": "etd_date_from",
            "label": __("ETD Date From"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.month_start()
        },
        {
            "fieldname": "workflow_state",
            "label": __("Status"),
            "fieldtype": "Select",
            "options": "\nUnconfirmed\nEmpty TO Head\nConfirmed\nShipped\nETA Passed\nArrived\nUndelivered\nDelivered\nCancelled",
            "default": ""
        }
    ]
};