import frappe
from frappe.email.smtp import SMTPServer
from hksoho.utils.ms365_smtp_wrapper import send_ms365_email

def send_ms365_email_hook(email_account, recipients, message, subject, **kwargs):
    """自定義 MS365 SMTP 發送邏輯"""
    send_ms365_email(recipients=recipients, subject=subject, content=message)

def override_smtp_send():
    """覆蓋 Frappe 的 SMTP 發送方法"""
    frappe.email.smtp.SMTPServer.send = send_ms365_email_hook

def setup_email():
    override_smtp_send()
    frappe.msgprint(_("MS365 SMTP has been configured"))

frappe.get_hooks().setdefault("app_include_hooks", []).append("hksoho.utils.email_utils.setup_email")
