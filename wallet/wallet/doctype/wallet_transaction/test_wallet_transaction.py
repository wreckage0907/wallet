# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Transaction controller.

Beside the controller rather than under `wallet/tests/`, because it is a doctype we own -
see `specs/testing.md`.

The controller is where four separate concerns meet on every save: validation, the sign
convention, auto-categorization and the dedup fingerprint. Three of them have a
"once, on insert" rule attached, and those rules are the ones worth pinning:

* a category chosen by hand is never overwritten by a later edit
* `dedup_hash` is stamped on insert and never recomputed
* a rule's match is counted when a transaction is created, not when one is previewed
"""

import frappe
from frappe.tests import IntegrationTestCase, change_settings, set_user

from wallet.tests.fixtures import (
	commit,
	make_account,
	make_category,
	make_rule,
	make_transaction,
	make_user,
	purge,
)


class TestWalletTransactionValidation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("txn-validate@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.account = make_account("Txn Savings", opening_balance=1000, opening_date="2026-01-01")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def test_a_non_positive_amount_is_refused(self):
		"""Direction carries the sign, so a negative amount is a second, contradictory way
		to say the same thing."""
		with set_user(self.user):
			for amount in (0, -100):
				with self.subTest(amount=amount), self.assertRaises(frappe.ValidationError):
					make_transaction(self.account, "2026-04-01", "Out", amount, "Txn bad amount")

	def test_direction_out_stores_a_negative_signed_amount(self):
		"""`signed_amount` is what every balance aggregate sums, so the sign lives there
		and `amount` stays a magnitude the UI can print."""
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "Txn out")

		doc = frappe.get_doc("Wallet Transaction", name)
		self.assertEqual(doc.amount, 250)
		self.assertEqual(doc.signed_amount, -250)

	def test_direction_in_stores_a_positive_signed_amount(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "In", 250, "Txn in")

		self.assertEqual(frappe.db.get_value("Wallet Transaction", name, "signed_amount"), 250)

	def test_a_date_before_the_account_opened_is_refused(self):
		"""The balance aggregate starts at the opening balance, so such a row would be
		silently excluded from every total rather than merely early."""
		with set_user(self.user), self.assertRaises(frappe.ValidationError):
			make_transaction(self.account, "2025-12-31", "Out", 100, "Txn too early")

	def test_a_transaction_on_the_opening_date_itself_is_allowed(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-01-01", "Out", 100, "Txn opening day")

		self.assertTrue(frappe.db.exists("Wallet Transaction", name))

	def test_the_sign_is_recomputed_when_the_direction_is_edited(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 100, "Txn flip")
			doc = frappe.get_doc("Wallet Transaction", name)
			doc.direction = "In"
			doc.save()

		self.assertEqual(frappe.db.get_value("Wallet Transaction", name, "signed_amount"), 100)


class TestWalletTransactionCategorization(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("txn-categorize@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.account = make_account("Txn Cat Savings")
			cls.food = make_category("Txn Food")
			cls.travel = make_category("Txn Travel")
			cls.rule = make_rule("Txn swiggy", "SWIGGY", cls.food, set_counterparty="Swiggy")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def times_matched(self) -> int:
		return frappe.db.get_value("Wallet Categorization Rule", self.rule, "times_matched") or 0

	def test_a_matching_narration_is_categorized_on_insert(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "UPI-SWIGGY ORDER 1")

		doc = frappe.get_doc("Wallet Transaction", name)
		self.assertEqual(doc.category, self.food)
		self.assertEqual(doc.counterparty, "Swiggy")

	def test_a_category_chosen_by_hand_is_never_overwritten(self):
		with set_user(self.user):
			name = make_transaction(
				self.account, "2026-04-01", "Out", 250, "UPI-SWIGGY ORDER 2", category=self.travel
			)

		self.assertEqual(frappe.db.get_value("Wallet Transaction", name, "category"), self.travel)

	def test_a_later_edit_does_not_re_categorize(self):
		"""Clearing a category by hand is a decision. Re-running the rules on the next save
		would quietly undo it."""
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "UPI-SWIGGY ORDER 3")
			doc = frappe.get_doc("Wallet Transaction", name)
			doc.category = None
			doc.save()

		self.assertIsNone(frappe.db.get_value("Wallet Transaction", name, "category"))

	@change_settings("Wallet Settings", {"auto_categorize": 0})
	def test_categorization_can_be_turned_off(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "UPI-SWIGGY ORDER 4")

		self.assertIsNone(frappe.db.get_value("Wallet Transaction", name, "category"))

	def test_creating_a_transaction_counts_the_rule_that_matched(self):
		before = self.times_matched()

		with set_user(self.user):
			make_transaction(self.account, "2026-04-01", "Out", 250, "UPI-SWIGGY ORDER 5")

		self.assertEqual(self.times_matched(), before + 1)

	def test_a_transaction_nothing_matched_counts_nothing(self):
		before = self.times_matched()

		with set_user(self.user):
			make_transaction(self.account, "2026-04-01", "Out", 250, "NEFT SOMETHING ELSE")

		self.assertEqual(self.times_matched(), before)

	def test_editing_a_transaction_does_not_count_the_rule_again(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "UPI-SWIGGY ORDER 6")
			before = self.times_matched()

			doc = frappe.get_doc("Wallet Transaction", name)
			doc.notes = "touched"
			doc.save()

		self.assertEqual(self.times_matched(), before)


class TestWalletTransactionDedupHash(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("txn-dedup@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.account = make_account("Txn Dedup Savings")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def test_every_transaction_is_stamped_with_a_fingerprint(self):
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "Txn hashed")

		self.assertTrue(frappe.db.get_value("Wallet Transaction", name, "dedup_hash"))

	def test_the_fingerprint_is_never_recomputed_on_a_later_save(self):
		"""It identifies the statement row this transaction came from, so correcting the
		transaction must not move it. Recomputing would also re-derive an occurrence
		ordinal that now collides with the row it was meant to distinguish."""
		with set_user(self.user):
			name = make_transaction(self.account, "2026-04-01", "Out", 250, "Txn stable hash")
			original = frappe.db.get_value("Wallet Transaction", name, "dedup_hash")

			doc = frappe.get_doc("Wallet Transaction", name)
			doc.description = "Txn description corrected"
			doc.amount = 999
			doc.save()

		self.assertEqual(frappe.db.get_value("Wallet Transaction", name, "dedup_hash"), original)

	def test_a_repeated_reference_number_is_rejected_by_the_unique_index(self):
		"""The database is the last line: `dedup_hash` is UNIQUE, so a second copy of the
		same payment cannot land however it got here."""
		with set_user(self.user):
			make_transaction(self.account, "2026-04-01", "Out", 250, "Txn ref", reference_number="UTR900")

			with self.assertRaises(frappe.UniqueValidationError):
				make_transaction(
					self.account, "2026-04-02", "Out", 400, "Txn ref again", reference_number="UTR900"
				)

	def test_two_identical_entries_without_a_reference_are_both_allowed(self):
		"""Two cash payments of the same amount to the same place on one day are a real
		thing that happens, and the occurrence ordinal is what keeps them apart."""
		with set_user(self.user):
			first = make_transaction(self.account, "2026-04-03", "Out", 50, "Txn chai")
			second = make_transaction(self.account, "2026-04-03", "Out", 50, "Txn chai")

		self.assertNotEqual(
			frappe.db.get_value("Wallet Transaction", first, "dedup_hash"),
			frappe.db.get_value("Wallet Transaction", second, "dedup_hash"),
		)


class TestWalletTransactionBalanceRefresh(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("txn-balance@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.savings = make_account("Txn Bal Savings", opening_balance=1000)
			cls.current = make_account("Txn Bal Current", opening_balance=2000)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def cached(self, account):
		return frappe.db.get_value("Wallet Account", account, "cached_balance")

	def test_inserting_refreshes_the_accounts_cached_balance(self):
		with set_user(self.user):
			name = make_transaction(self.savings, "2026-04-01", "Out", 100, "Txn refresh insert")

		self.assertEqual(self.cached(self.savings), 900)

		with set_user(self.user):
			frappe.delete_doc("Wallet Transaction", name)

	def test_deleting_refreshes_it_again(self):
		"""Hooked on `after_delete`, not `on_trash`: `on_trash` runs while the row is still
		in the table, so the aggregate would still count the transaction being removed."""
		with set_user(self.user):
			name = make_transaction(self.savings, "2026-04-01", "Out", 300, "Txn refresh delete")
			self.assertEqual(self.cached(self.savings), 700)

			frappe.delete_doc("Wallet Transaction", name)

		self.assertEqual(self.cached(self.savings), 1000)

	def test_moving_a_transaction_between_accounts_refreshes_both(self):
		"""Only the new account would be refreshed if the previous one were not looked up,
		leaving the old one permanently overstating."""
		with set_user(self.user):
			name = make_transaction(self.savings, "2026-04-01", "Out", 500, "Txn moved")
			doc = frappe.get_doc("Wallet Transaction", name)
			doc.account = self.current
			doc.save()

		self.assertEqual(self.cached(self.savings), 1000)
		self.assertEqual(self.cached(self.current), 1500)

		with set_user(self.user):
			frappe.delete_doc("Wallet Transaction", name)

	def test_the_bulk_import_flag_suppresses_the_per_row_refresh(self):
		"""A 5,000 row import would otherwise run a full account aggregate 5,000 times.
		The importer sets this flag and refreshes once at the end."""
		frappe.db.set_value("Wallet Account", self.savings, "cached_balance", 1000, update_modified=False)
		frappe.flags.wallet_bulk_import = True
		try:
			with set_user(self.user):
				name = make_transaction(self.savings, "2026-04-01", "Out", 100, "Txn bulk")
		finally:
			frappe.flags.wallet_bulk_import = False

		self.assertEqual(self.cached(self.savings), 1000)

		with set_user(self.user):
			frappe.delete_doc("Wallet Transaction", name)
