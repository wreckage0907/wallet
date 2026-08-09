# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from wallet.settings import get_setting
from wallet.utils.dedup import build_dedup_hash


class WalletTransaction(Document):
	def validate(self) -> None:
		self.validate_amount()
		self.set_signed_amount()
		self.validate_against_opening_date()
		self.apply_categorization()
		self.set_dedup_hash()

	def validate_amount(self) -> None:
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero. Use Direction to record money going out."))

	def set_signed_amount(self) -> None:
		self.signed_amount = flt(self.amount) if self.direction == "In" else -flt(self.amount)

	def validate_against_opening_date(self) -> None:
		"""A transaction before the account's opening date would be silently excluded from
		the balance aggregate, so reject it rather than quietly lose it."""
		opening_date = frappe.db.get_value("Wallet Account", self.account, "opening_date")
		if opening_date and self.posting_date and frappe.utils.getdate(self.posting_date) < frappe.utils.getdate(opening_date):
			frappe.throw(
				_("{0} is before this account's opening date ({1}). Move the opening date back first.").format(
					frappe.format(self.posting_date, {"fieldtype": "Date"}),
					frappe.format(opening_date, {"fieldtype": "Date"}),
				)
			)

	def apply_categorization(self) -> None:
		"""Auto-categorize only on first save and only when no category was chosen, so a
		manual override is never clobbered by a later edit."""
		if self.category or not self.is_new():
			return

		# Deliberately get_setting, not frappe.db.get_single_value: on a site where
		# Wallet Settings has never been saved the latter reports 0 rather than the
		# field's declared default of 1, and auto-categorization would silently never run.
		if not get_setting("auto_categorize"):
			return

		if not frappe.db.table_exists("Wallet Categorization Rule"):
			return

		from wallet.categorization import categorize

		match = categorize(self.as_dict())
		self._matched_rule = match.pop("rule", None)

		for field, value in match.items():
			if value and not self.get(field):
				self.set(field, value)

	def set_dedup_hash(self) -> None:
		"""Stamp the fingerprint once, on insert, and never recompute it.

		Recomputing on every save would break the weakest dedup tier: editing the first of
		two identical rows would re-derive an occurrence ordinal that now collides with the
		second. The fingerprint identifies the statement row this transaction came from, so
		it should not move when the transaction is later corrected.
		"""
		if self.dedup_hash:
			return

		self.dedup_hash = build_dedup_hash(
			account=self.account,
			posting_date=self.posting_date,
			signed_amount=self.signed_amount,
			description=self.description,
			reference_number=self.reference_number,
			balance_after=self.balance_after,
			exclude=self.name if not self.is_new() else None,
		)

	def after_insert(self) -> None:
		from wallet.categorization import record_match

		# Counted here, not during categorization, so previewing an import does not
		# inflate the tally.
		record_match(getattr(self, "_matched_rule", None))

	def on_update(self) -> None:
		self.refresh_account_balance()

	def after_delete(self) -> None:
		# Deliberately after_delete, not on_trash: on_trash runs *before* the row leaves
		# the table, so the aggregate would still count the transaction being removed.
		self.refresh_account_balance()

	def refresh_account_balance(self) -> None:
		"""Keep `cached_balance` fresh. This is a display convenience only: because it is
		written by the same aggregate that reads, staleness is the worst failure mode -
		it can never drift by accumulation the way an incremental counter does."""
		# A statement import inserts thousands of rows in one go. Recomputing the account
		# aggregate per row makes the import quadratic, so the importer sets this flag and
		# refreshes the affected account exactly once at the end.
		if frappe.flags.wallet_bulk_import:
			return

		from wallet.api.balance import refresh_cached_balance

		refresh_cached_balance(self.account)

		previous = self.get_doc_before_save()
		if previous and previous.account and previous.account != self.account:
			refresh_cached_balance(previous.account)
