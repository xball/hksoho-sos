# Copyright (c) 2025, HKSoHo and contributors
# For license information, please see license.txt

# import frappe
from datetime import datetime
import isoweek
from frappe.model.document import Document

class PurchaseOrderItem(Document):
    def before_save(self):
        self.update_remaining_qty()

    def update_remaining_qty(self):
        # 確保數值存在且為數字，避免 None 或空值
        confirmed = self.get("confirmed_qty") or 0
        delivery = self.get("delivery_qty") or 0
        
        # 計算剩餘數量（不允許負數，可依需求調整）
        self.remaining_qty = max(confirmed - delivery, 0)

    # 如果有修改 confirmed_qty 或 delivery_qty 時也要即時更新
    def on_update(self):
        # 如果這是 child table，在 parent 保存時會觸發所有 child 的 on_update
        self.update_remaining_qty()