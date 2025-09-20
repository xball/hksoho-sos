import frappe
from frappe import _
from O365 import Account, MSGraphProtocol
import logging

# 設置日誌
logging.basicConfig(
    filename='/home/frappe/logs/frappe.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)

class MS365SMTPWrapper:
    def __init__(self):
        """從 site_config.json 初始化 MS365 憑證"""
        self.client_id = frappe.conf.get("ms365_client_id")
        self.client_secret = frappe.conf.get("ms365_client_secret")
        self.tenant_id = frappe.conf.get("ms365_tenant_id")
        self.user_email = frappe.conf.get("ms365_user_email")
        if not all([self.client_id, self.client_secret, self.tenant_id, self.user_email]):
            frappe.throw(_("Missing MS365 SMTP configuration in site_config.json"))
        self.account = None
        self.protocol = MSGraphProtocol()

    def authenticate(self):
        """認證 MS365 帳戶"""
        try:
            credentials = (self.client_id, self.client_secret)
            self.account = Account(
                credentials,
                auth_flow_type='credentials',
                tenant_id=self.tenant_id,
                protocol=self.protocol
            )
            if not self.account.is_authenticated:
                self.account.authenticate()
            if not self.account.is_authenticated:
                frappe.throw(_("Failed to authenticate with MS365"))
        except Exception as e:
            logging.error(f"Authentication error: {str(e)}")
            frappe.log_error(f"Authentication error: {str(e)}")
            frappe.throw(_("Authentication error: {0}").format(str(e)))

    def send_email(self, recipients, subject, content, sender=None):
        """使用 MS365 SMTP 發送電子郵件"""
        if not self.account:
            self.authenticate()

        try:
            mailbox = self.account.mailbox(self.user_email)
            message = mailbox.new_message()
            message.to.add(recipients if isinstance(recipients, list) else [recipients])
            message.subject = subject
            message.body = content
            message.sender.address = sender or self.user_email
            message.send()
            frappe.msgprint(_("Email sent successfully"))
        except Exception as e:
            logging.error(f"Failed to send email: {str(e)}")
            frappe.log_error(f"Failed to send email: {str(e)}")
            frappe.throw(_("Failed to send email: {0}").format(str(e)))

def send_ms365_email(recipients, subject, content):
    """Frappe 可調用的封裝函數"""
    smtp = MS365SMTPWrapper()
    smtp.send_email(recipients, subject, content)

# 僅用於獨立測試（應在 Frappe 環境中移除）
if __name__ == "__main__":
    try:
        send_ms365_email(
            recipients=["recipient@example.com"],
            subject="Test Email from Frappe",
            content="This is a test email sent via MS365 using O365 library."
        )
    except Exception as e:
        logging.error(f"Test email failed: {str(e)}")
        print(f"Test email failed: {str(e)}")
