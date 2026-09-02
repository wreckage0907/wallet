# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the manual transaction write path.

`wallet.api.transaction_api.create_transaction` is whitelisted, so unlike the MCP tools
its arguments arrive straight off the wire from anyone holding a session. The account and
category it is handed are `autoname: hash` docnames - guessable in principle, and neither
`doc.insert()` nor Frappe's link validation checks that they belong to the caller. The
isolation tests below are the ones that matter; the rest cover the paths where a
mis-typed entry has to come back as something a person can read.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.api.transaction_api import create_transaction
from wallet.tests.fixtures import make_account, make_category, make_user, purge


class TestTransactionAPI(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("txn-api-alice@example.com")
		cls.bob = make_user("txn-api-bob@example.com")

		# This suite runs against a real dev database, so it owns its fixtures end to end.
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.alice_account = make_account("Alice API Savings")
			cls.alice_category = make_category("Alice API Groceries")

		with set_user(cls.bob):
			cls.bob_account = make_account("Bob API Current")
			cls.bob_category = make_category("Bob API Groceries")

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		frappe.db.commit()
		super().tearDownClass()

	# --- isolation --------------------------------------------------------------------

	def test_cannot_post_onto_another_holders_account(self):
		"""The whole reason the account is permission-checked by hand: `doc.insert()`
		checks only that Alice may create a transaction, and link validation checks only
		that Bob's account exists."""
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			create_transaction(self.bob_account, "2026-08-05", "Out", 100, description="Alice trespass")

	def test_cannot_borrow_another_holders_category(self):
		"""A category id is not personal data on its own - the response echoing back its
		name is."""
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			create_transaction(
				self.alice_account,
				"2026-08-05",
				"Out",
				100,
				description="Alice borrowed category",
				category=self.bob_category,
			)

	def test_a_refused_write_leaves_nothing_behind(self):
		with set_user(self.alice):
			before = frappe.db.count("Wallet Transaction", {"account": self.alice_account})
			with self.assertRaises(frappe.PermissionError):
				create_transaction(self.bob_account, "2026-08-05", "Out", 100, description="Alice trespass 2")
			after = frappe.db.count("Wallet Transaction", {"account": self.alice_account})

		self.assertEqual(before, after)

	# --- the happy path ---------------------------------------------------------------

	def test_records_the_transaction_and_the_balance_it_leaves(self):
		# Its own account, because the returned balance is an absolute figure: asserting on
		# it against the shared fixture account would make this test depend on which of the
		# sibling tests unittest happened to run first.
		with set_user(self.alice):
			account = make_account("Alice API Balance Probe")
			result = create_transaction(account, "2026-08-05", "Out", 250, description="Alice coffee")

		self.assertTrue(result["created"])
		self.assertEqual(result["transaction"]["amount"], 250)
		self.assertEqual(result["transaction"]["direction"], "Out")
		self.assertEqual(result["transaction"]["account_name"], "Alice API Balance Probe")
		self.assertEqual(result["account_balance"], -250)

	def test_the_chosen_category_is_kept(self):
		with set_user(self.alice):
			result = create_transaction(
				self.alice_account,
				"2026-08-06",
				"Out",
				90,
				description="Alice chosen category",
				category=self.alice_category,
			)

		self.assertEqual(result["transaction"]["category"], self.alice_category)
		self.assertEqual(result["transaction"]["category_name"], "Alice API Groceries")

	def test_a_future_entry_reports_the_balance_as_of_its_own_date(self):
		"""get_account_balance defaults to today and filters `posting_date <= as_on`, so
		reporting as of today would echo a balance the entry had no effect on."""
		future = frappe.utils.add_days(frappe.utils.nowdate(), 30)
		with set_user(self.alice):
			result = create_transaction(self.alice_account, future, "In", 500, description="Alice future")

		self.assertEqual(result["balance_as_on"], future)
		self.assertIn("Alice future", str(result["transaction"]["description"]))

	def test_accepts_lowercase_direction(self):
		with set_user(self.alice):
			result = create_transaction(
				self.alice_account, "2026-08-07", "in", 40, description="Alice lowercase"
			)

		self.assertEqual(result["transaction"]["direction"], "In")

	# --- rejections -------------------------------------------------------------------

	def test_rejects_a_bad_direction(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			create_transaction(self.alice_account, "2026-08-05", "sideways", 100)

	def test_rejects_a_non_positive_amount(self):
		"""Direction carries the sign, so a negative amount is a caller that has
		misunderstood the contract - not a withdrawal."""
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			create_transaction(self.alice_account, "2026-08-05", "Out", -100)

		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			create_transaction(self.alice_account, "2026-08-05", "Out", 0)

	def test_rejects_a_date_before_the_account_opened(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			create_transaction(self.alice_account, "2019-01-01", "Out", 100, description="Alice too early")

	# --- duplicates -------------------------------------------------------------------

	def test_a_colliding_entry_is_named_not_raised_as_a_sql_error(self):
		"""`dedup_hash` is UNIQUE. Caught here, the caller can say "you already recorded
		this on the 8th"; uncaught, MariaDB raises 1062 and the user sees an error code."""
		with set_user(self.alice):
			first = create_transaction(
				self.alice_account,
				"2026-08-08",
				"Out",
				77,
				description="Alice UTR probe",
				reference_number="UTR-API-0001",
			)
			second = create_transaction(
				self.alice_account,
				"2026-08-08",
				"Out",
				77,
				description="Alice UTR probe",
				reference_number="UTR-API-0001",
			)

		self.assertTrue(first["created"])
		self.assertFalse(second["created"])
		self.assertEqual(second["reason"], "duplicate")
		self.assertEqual(second["duplicate_of"]["id"], first["transaction"]["id"])

	def test_a_repeated_cash_entry_is_two_real_transactions(self):
		"""The counterpart to the test above, and the reason the duplicate check cannot
		simply compare fields: two identical chai payments on one day are not a mistake.
		build_dedup_hash keeps them distinct by occurrence ordinal - see utils/dedup.py."""
		with set_user(self.alice):
			first = create_transaction(self.alice_account, "2026-08-09", "Out", 60, description="Alice chai")
			second = create_transaction(self.alice_account, "2026-08-09", "Out", 60, description="Alice chai")

		self.assertTrue(first["created"])
		self.assertTrue(second["created"])
		self.assertNotEqual(first["transaction"]["id"], second["transaction"]["id"])
