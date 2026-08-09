# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class WalletCategorizationRule(Document):
	def validate(self) -> None:
		self.validate_pattern()
		self.validate_amount_range()

	def validate_pattern(self) -> None:
		if self.match_type != "Regex":
			return

		try:
			re.compile(self.pattern)
		except re.error as e:
			frappe.throw(_("Invalid regular expression: {0}").format(e))

	def validate_amount_range(self) -> None:
		if self.amount_min and self.amount_max and self.amount_min > self.amount_max:
			frappe.throw(_("Minimum amount cannot exceed maximum amount."))
