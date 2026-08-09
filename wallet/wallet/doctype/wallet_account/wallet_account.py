# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

#: Account types whose balance is money owed rather than money held.
LIABILITY_TYPES = ("Credit Card", "Loan")


class WalletAccount(Document):
	def validate(self) -> None:
		self.is_liability = int(self.account_type in LIABILITY_TYPES)
		self.validate_unique_name()
		self.validate_masked_number()

	def validate_unique_name(self) -> None:
		"""Account names are unique per user - autoname is `hash` so two people can each
		have a "HDFC Savings"."""
		if frappe.db.exists(
			"Wallet Account",
			{"account_name": self.account_name, "owner": self.owner, "name": ["!=", self.name]},
		):
			frappe.throw(_("You already have an account named {0}.").format(frappe.bold(self.account_name)))

	def validate_masked_number(self) -> None:
		"""Count digits, not characters.

		A length check let an unmasked eight-digit account number through while the field
		promises only the last four are kept. Masking characters are still welcome, so
		"****1234" passes and "12345678" does not.
		"""
		if not self.masked_account_number:
			return

		digits = sum(1 for ch in self.masked_account_number if ch.isdigit())
		if digits > 4:
			frappe.throw(
				_("Store only the last four digits of the account number (masking characters are fine).")
			)

	def on_update(self) -> None:
		self.refresh_cached_balance()

	@frappe.whitelist()
	def refresh_cached_balance(self) -> float:
		from wallet.api.balance import get_account_balance

		balance = get_account_balance(self.name)["balance"]
		frappe.db.set_value(
			"Wallet Account",
			self.name,
			{"cached_balance": balance, "balance_last_updated": frappe.utils.now()},
			update_modified=False,
		)
		return balance
