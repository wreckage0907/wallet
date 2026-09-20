# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.api.transaction_api`.

Deliberately thin. `create_transaction` is a whitelisted wrapper around behaviour that is
already covered underneath it - the amount and opening-date rules by the Wallet
Transaction controller, the fingerprint tiers by `tests/utils/test_dedup.py`, and the
direction and duplicate paths again by `tests/mcp/test_tools.py`, which since this module
landed calls the very same function. Re-asserting any of that here would add tests that
can only ever fail as a block.

What is left is what only exists at this door:

* the two `frappe.has_permission` checks. They are the only thing standing between a
  session and another holder's account, because the ids arrive over HTTP and neither
  `doc.insert()` nor Frappe's link validation looks at who owns the row being linked.
* the disabled-record refusals, for the same reason: every caller filters those out
  before offering them, so only a stale form or a hand-made request gets this far.
* the response contract the PWA's Add screen reads - the resulting balance, the resolved
  category, and the duplicate that comes back as a value rather than an exception.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, set_user
from frappe.utils import add_days, nowdate

from wallet.api import transaction_api
from wallet.api.transaction_api import create_transaction
from wallet.tests.fixtures import commit, make_account, make_category, make_user, purge


class TestCreateTransaction(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("txn-api-alice@example.com")
		cls.bob = make_user("txn-api-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.savings = make_account("Txn API Savings")
			cls.groceries = make_category("Txn API Groceries")

			# Disabled after the fact, through db.set_value, so validation does not reject
			# the fixture on its way in.
			cls.closed = make_account("Txn API Closed")
			cls.retired = make_category("Txn API Retired")
			frappe.db.set_value("Wallet Account", cls.closed, "disabled", 1)
			frappe.db.set_value("Wallet Category", cls.retired, "disabled", 1)

		with set_user(cls.bob):
			cls.bob_account = make_account("Txn API Bob Current")
			cls.bob_category = make_category("Txn API Bob Groceries")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	# --- isolation --------------------------------------------------------------------

	def test_a_transaction_cannot_be_posted_onto_another_holders_account(self):
		"""The reason the account is permission-checked by hand. `doc.insert()` asks only
		whether Alice may create a transaction, and link validation asks only whether the
		account exists - neither notices whose it is.

		Note this is not the same ground as the MCP suite's cross-holder write: that one
		passes an account *name*, which dies in `resolve.account` long before any
		permission check. The PWA passes a docname, which does not."""
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			create_transaction(self.bob_account, nowdate(), "Out", 100, description="Alice trespass")

	def test_another_holders_category_cannot_be_borrowed(self):
		"""A category id is not personal data on its own. The response echoing its name
		back is."""
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			create_transaction(
				self.savings,
				nowdate(),
				"Out",
				100,
				description="Alice borrowed category",
				category=self.bob_category,
			)

	def test_the_permission_check_runs_before_the_insert(self):
		"""Refused *after* the insert would be no better than allowed: the row would be
		sitting in the other holder's account either way."""
		with set_user(self.alice):
			with self.assertRaises(frappe.PermissionError):
				create_transaction(self.bob_account, nowdate(), "Out", 100, description="Alice trespass 2")

			landed = frappe.db.count("Wallet Transaction", {"description": "Alice trespass 2"})

		self.assertEqual(landed, 0)

	# --- records nobody was offered ---------------------------------------------------

	def test_a_closed_account_is_refused(self):
		"""Owning an account is not the same as being able to file against it. Worse than
		refusing: `get_overview` excludes disabled accounts, so the spend would be real and
		invisible on every screen that could have shown it."""
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			create_transaction(self.closed, nowdate(), "Out", 100, description="Alice on a closed account")

	def test_a_retired_category_is_refused(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			create_transaction(
				self.savings,
				nowdate(),
				"Out",
				100,
				description="Alice retired category",
				category=self.retired,
			)

	# --- the response contract --------------------------------------------------------

	def test_it_reports_the_balance_the_entry_leaves_behind(self):
		"""The balance echo is the whole point of returning anything: it is where a
		misread amount becomes visible. Its own account, because the figure is absolute -
		asserting it against the shared fixture would make this test depend on which
		sibling ran first."""
		with set_user(self.alice):
			account = make_account("Txn API Balance Probe", opening_balance=1000)
			result = create_transaction(account, "2026-08-05", "Out", 250, description="Alice coffee")

		self.assertTrue(result["created"])
		self.assertEqual(result["transaction"]["amount"], 250)
		self.assertEqual(result["transaction"]["account_name"], "Txn API Balance Probe")
		self.assertEqual(result["account_balance"], 750)

	def test_a_future_entry_reports_the_balance_as_of_its_own_date(self):
		"""`get_account_balance` defaults to today and filters `posting_date <= as_on`, so
		reporting as of today would echo a balance the entry had no effect on - for exactly
		the entries most likely to be mis-typed."""
		future = add_days(nowdate(), 30)
		with set_user(self.alice):
			result = create_transaction(self.savings, future, "In", 500, description="Alice future")

		self.assertEqual(result["balance_as_on"], future)

	def test_the_category_comes_back_resolved(self):
		"""The screen shows what the entry was filed under, and when the field was left
		blank that is whatever a rule chose - so the id alone is not enough."""
		with set_user(self.alice):
			result = create_transaction(
				self.savings,
				"2026-08-06",
				"Out",
				90,
				description="Alice chosen category",
				category=self.groceries,
			)

		self.assertEqual(result["transaction"]["category"], self.groceries)
		self.assertEqual(result["transaction"]["category_name"], "Txn API Groceries")

	def test_a_collision_is_a_value_not_an_exception(self):
		"""`dedup_hash` is UNIQUE, and the screen has to be able to say "you already
		recorded this on the 7th" - so the duplicate comes back as a return value with the
		row it collided with, not as a throw the caller has to parse."""
		with set_user(self.alice):
			first = create_transaction(
				self.savings,
				"2026-08-07",
				"Out",
				77,
				description="Alice UTR probe",
				reference_number="UTR-API-0001",
			)
			second = create_transaction(
				self.savings,
				"2026-08-07",
				"Out",
				77,
				description="Alice UTR probe",
				reference_number="UTR-API-0001",
			)

		self.assertTrue(first["created"])
		self.assertFalse(second["created"])
		self.assertEqual(second["reason"], "duplicate")
		self.assertEqual(second["duplicate_of"]["id"], first["transaction"]["id"])
		self.assertEqual(second["duplicate_of"]["posting_date"], "2026-08-07")

	def test_a_collision_that_beats_the_pre_check_is_still_not_a_sql_error(self):
		"""The pre-check is a read and the insert is a write, so they are not atomic: a
		save that raced this one lands the fingerprint the check just cleared. Losing that
		race is indistinguishable, from inside the function, from the check simply not
		seeing the row - so that is what is simulated here, once, leaving the recovery path
		to find it for real.

		Also the only test that exercises the savepoint: without it the failed statement
		would leave the transaction unusable and the re-query below would not run at all."""
		real = transaction_api.find_duplicate
		seen = []

		def blind_the_first_look(*args, **kwargs):
			seen.append(1)
			return None if len(seen) == 1 else real(*args, **kwargs)

		with set_user(self.alice):
			first = create_transaction(
				self.savings,
				"2026-08-11",
				"Out",
				55,
				description="Alice raced",
				reference_number="UTR-API-RACE",
			)

			with patch.object(transaction_api, "find_duplicate", side_effect=blind_the_first_look):
				second = create_transaction(
					self.savings,
					"2026-08-11",
					"Out",
					55,
					description="Alice raced",
					reference_number="UTR-API-RACE",
				)

		self.assertTrue(first["created"])
		self.assertFalse(second["created"])
		self.assertEqual(second["reason"], "duplicate")
		self.assertEqual(second["duplicate_of"]["id"], first["transaction"]["id"])
