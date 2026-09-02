# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Account controller.

Two of the three rules here exist because the doctype is `autoname: hash`. That is what
lets two holders each keep an account called "HDFC Savings", and it is also what makes
"unique" a per-owner question the database cannot answer on its own.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.tests.fixtures import commit, make_account, make_transaction, make_user, purge


class TestWalletAccount(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("acct-alice@example.com")
		cls.bob = make_user("acct-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.savings = make_account("Acct Savings", opening_balance=1000)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	# --- liability flag ---------------------------------------------------------------

	def test_a_credit_card_is_a_liability(self):
		with set_user(self.alice):
			card = make_account("Acct Card", account_type="Credit Card")

		self.assertEqual(frappe.db.get_value("Wallet Account", card, "is_liability"), 1)

	def test_a_loan_is_a_liability(self):
		with set_user(self.alice):
			loan = make_account("Acct Loan", account_type="Loan")

		self.assertEqual(frappe.db.get_value("Wallet Account", loan, "is_liability"), 1)

	def test_a_savings_account_is_not(self):
		self.assertEqual(frappe.db.get_value("Wallet Account", self.savings, "is_liability"), 0)

	def test_the_flag_is_derived_not_accepted(self):
		"""It is set from `account_type` on every save, so a value posted by a client - or
		left over from an earlier type - cannot survive."""
		with set_user(self.alice):
			account = make_account("Acct Derived", account_type="Savings")
			doc = frappe.get_doc("Wallet Account", account)
			doc.is_liability = 1
			doc.save()

		self.assertEqual(frappe.db.get_value("Wallet Account", account, "is_liability"), 0)

	def test_changing_the_type_moves_the_flag_with_it(self):
		with set_user(self.alice):
			account = make_account("Acct Retyped", account_type="Savings")
			doc = frappe.get_doc("Wallet Account", account)
			doc.account_type = "Credit Card"
			doc.save()

		self.assertEqual(frappe.db.get_value("Wallet Account", account, "is_liability"), 1)

	# --- unique names -----------------------------------------------------------------

	def test_the_same_holder_cannot_have_two_accounts_of_one_name(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			make_account("Acct Savings")

	def test_two_holders_can_each_have_an_account_of_the_same_name(self):
		"""The reason `autoname` is `hash` rather than the account name."""
		with set_user(self.bob):
			bobs = make_account("Acct Savings")

		self.assertNotEqual(bobs, self.savings)
		self.assertEqual(frappe.db.get_value("Wallet Account", bobs, "owner"), self.bob)

	def test_renaming_an_account_to_its_own_name_is_fine(self):
		"""The uniqueness check excludes the document being saved, or no account could
		ever be edited again."""
		with set_user(self.alice):
			doc = frappe.get_doc("Wallet Account", self.savings)
			doc.opening_balance = 1500
			doc.save()

		self.assertEqual(frappe.db.get_value("Wallet Account", self.savings, "opening_balance"), 1500)
		frappe.db.set_value("Wallet Account", self.savings, "opening_balance", 1000)

	# --- masked number ----------------------------------------------------------------

	def test_more_than_four_digits_is_refused(self):
		"""The field promises only the last four are kept, and a length check let a bare
		eight-digit account number through."""
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			make_account("Acct Unmasked", masked_account_number="12345678")

	def test_masking_characters_do_not_count_as_digits(self):
		with set_user(self.alice):
			account = make_account("Acct Masked", masked_account_number="****1234")

		self.assertEqual(frappe.db.get_value("Wallet Account", account, "masked_account_number"), "****1234")

	def test_exactly_four_digits_is_allowed(self):
		with set_user(self.alice):
			account = make_account("Acct Four", masked_account_number="XX4321")

		self.assertTrue(frappe.db.exists("Wallet Account", account))

	def test_no_masked_number_at_all_is_allowed(self):
		with set_user(self.alice):
			account = make_account("Acct Nomask", masked_account_number=None)

		self.assertTrue(frappe.db.exists("Wallet Account", account))

	# --- cached balance ---------------------------------------------------------------

	def test_saving_an_account_refreshes_its_cached_balance(self):
		"""Editing the opening balance changes the account balance without any transaction
		being touched, so the refresh has to hang off the account's own save."""
		with set_user(self.alice):
			account = make_account("Acct Cached", opening_balance=1000)
			make_transaction(account, "2026-04-01", "Out", 250, "Acct spend")

			doc = frappe.get_doc("Wallet Account", account)
			doc.opening_balance = 2000
			doc.save()

		self.assertEqual(frappe.db.get_value("Wallet Account", account, "cached_balance"), 1750)

	def test_the_refresh_method_returns_the_balance_it_stored(self):
		with set_user(self.alice):
			account = make_account("Acct Refresh", opening_balance=500)
			frappe.db.set_value("Wallet Account", account, "cached_balance", -1, update_modified=False)

			returned = frappe.get_doc("Wallet Account", account).refresh_cached_balance()

		self.assertEqual(returned, 500)
		self.assertEqual(frappe.db.get_value("Wallet Account", account, "cached_balance"), 500)
