# Copyright (c) 2025, HKSoHo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DeliveryTerm(Document):
    def before_save(self):
        self.display_name = f"{self.name} - {self.description}"
