親愛的 {{ doc.owner }}，

您的採購訂單 {{ doc.name }} 已於 {{ doc.modified }} 被批准。
當前狀態：{{ doc.workflow_state }}

請點擊以下鏈接查看詳情：
{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}

謝謝，
{{ frappe.db.get_value("User", frappe.session.user, "full_name") }}