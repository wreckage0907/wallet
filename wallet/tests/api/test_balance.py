# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.api.balance`.

A balance here is an aggregate, never a stored counter, and these tests are written to
hold that line: they assert the sum is right after an edit, after a delete and across a
date boundary, which is exactly where an incremental counter drifts.

The other thing under test is that every query stays permission-aware. `frappe.get_all`
bypasses `permission_query_conditions` entirely, so a single careless swap in this module
would put one holder's accounts in another's net worth. Every read here has a second
holder sitting beside it whose numbers must never appear.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.api.balance import (
	get_account_balance,
	get_cashflow,
	get_overview,
	rebuild_all_balances,
	rebuild_balances,
	refresh_cached_balance,
)
from wallet.tests.fixtures import commit, make_account, make_category, make_transaction, make_user, purge


class TestGetAccountBalance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("bal-alice@example.com")
		cls.bob = make_user("bal-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.savings = make_account("Bal Savings", opening_balance=1000)
			make_transaction(cls.savings, "2026-04-01", "In", 500, "April credit")
			make_transaction(cls.savings, "2026-05-01", "Out", 200, "May debit")

		with set_user(cls.bob):
			cls.bob_account = make_account("Bal Bob Savings", opening_balance=999999)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def test_the_balance_is_the_opening_balance_plus_every_movement(self):
		with set_user(self.alice):
			result = get_account_balance(self.savings, as_on="2026-06-01")

		self.assertEqual(result["opening_balance"], 1000)
		self.assertEqual(result["movement"], 300)
		self.assertEqual(result["balance"], 1300)

	def test_as_on_excludes_anything_dated_later(self):
		"""Same rows, an earlier date, a different answer - the property a stored counter
		cannot have."""
		with set_user(self.alice):
			self.assertEqual(get_account_balance(self.savings, as_on="2026-04-15")["balance"], 1500)
			self.assertEqual(get_account_balance(self.savings, as_on="2026-03-01")["balance"], 1000)

	def test_a_transaction_on_the_as_on_date_itself_counts(self):
		"""The filter is `<=`, and an off-by-one here would drop today's spending."""
		with set_user(self.alice):
			self.assertEqual(get_account_balance(self.savings, as_on="2026-04-01")["balance"], 1500)

	def test_it_reports_the_accounts_currency_and_liability_flag(self):
		with set_user(self.alice):
			result = get_account_balance(self.savings)

		self.assertEqual(result["currency"], "INR")
		self.assertIs(result["is_liability"], False)

	def test_another_holders_account_is_refused(self):
		"""`frappe.db.get_value` below the check reads any row on the site, so without the
		explicit permission check a guessed docname would leak a balance and a currency."""
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			get_account_balance(self.bob_account)

	def test_deleting_a_transaction_takes_it_straight_back_out_of_the_sum(self):
		with set_user(self.alice):
			extra = make_transaction(self.savings, "2026-05-02", "Out", 100, "Bal delete me")
			self.assertEqual(get_account_balance(self.savings, as_on="2026-06-01")["balance"], 1200)

			frappe.delete_doc("Wallet Transaction", extra)

			self.assertEqual(get_account_balance(self.savings, as_on="2026-06-01")["balance"], 1300)

	def test_editing_an_amount_is_reflected_without_any_fixup(self):
		with set_user(self.alice):
			extra = make_transaction(self.savings, "2026-05-02", "Out", 100, "Bal edit me")
			try:
				doc = frappe.get_doc("Wallet Transaction", extra)
				doc.amount = 400
				doc.save()

				self.assertEqual(get_account_balance(self.savings, as_on="2026-06-01")["balance"], 900)
			finally:
				frappe.delete_doc("Wallet Transaction", extra)


class TestGetOverview(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("ovw-alice@example.com")
		cls.bob = make_user("ovw-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.savings = make_account("Ovw Savings", opening_balance=100000)
			cls.card = make_account("Ovw Card", account_type="Credit Card")
			cls.excluded = make_account("Ovw Excluded", opening_balance=50000, include_in_net_worth=0)
			cls.dollars = make_account("Ovw Dollars", opening_balance=700, currency="USD")
			cls.closed = make_account("Ovw Closed", opening_balance=12345)

			make_transaction(cls.savings, "2026-04-01", "Out", 250, "Ovw coffee")
			make_transaction(cls.card, "2026-04-01", "Out", 4200, "Ovw groceries")
			frappe.db.set_value("Wallet Account", cls.closed, "disabled", 1)

		with set_user(cls.bob):
			cls.bob_account = make_account("Ovw Bob Canary", opening_balance=999999)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def overview(self, as_on="2026-06-01"):
		with set_user(self.alice):
			return get_overview(as_on=as_on)

	def names(self, overview):
		return {account["account_name"] for account in overview["accounts"]}

	def test_every_account_carries_its_own_balance(self):
		balances = {a["account_name"]: a["balance"] for a in self.overview()["accounts"]}

		self.assertEqual(balances["Ovw Savings"], 99750)
		self.assertEqual(balances["Ovw Card"], -4200)

	def test_a_spent_on_credit_card_lands_in_liabilities(self):
		"""The sign convention does the work; `is_liability` only changes the label."""
		overview = self.overview()

		self.assertEqual(overview["assets"], 99750)
		self.assertEqual(overview["liabilities"], 4200)
		self.assertEqual(overview["net_worth"], 95550)

	def test_liabilities_are_reported_as_a_positive_magnitude(self):
		"""It is rendered as "Owed ₹4,200", so a negative would read as money held."""
		self.assertGreater(self.overview()["liabilities"], 0)

	def test_an_account_excluded_from_net_worth_still_appears_but_does_not_count(self):
		overview = self.overview()

		self.assertIn("Ovw Excluded", self.names(overview))
		self.assertEqual(overview["net_worth"], 95550)

	def test_a_disabled_account_is_left_out_entirely(self):
		self.assertNotIn("Ovw Closed", self.names(self.overview()))

	def test_another_holders_accounts_never_appear(self):
		"""The canary holds the largest balance on the site, so a leak would also move
		every headline figure."""
		overview = self.overview()

		self.assertNotIn("Ovw Bob Canary", self.names(overview))
		self.assertLess(overview["net_worth"], 999999)

	def test_totals_are_kept_per_currency(self):
		"""Adding a rupee balance to a dollar balance gives a number that is wrong in both."""
		overview = self.overview()
		by_currency = {bucket["currency"]: bucket for bucket in overview["by_currency"]}

		self.assertEqual(by_currency["USD"]["assets"], 700)
		self.assertEqual(by_currency["INR"]["assets"], 99750)
		self.assertNotIn(700, (overview["assets"], overview["net_worth"]))

	def test_the_headline_figures_are_the_base_currency_only(self):
		overview = self.overview()

		self.assertEqual(overview["currency"], "INR")
		self.assertEqual(overview["net_worth"], 95550)

	def test_a_second_currency_is_flagged_so_the_ui_can_say_so(self):
		self.assertTrue(self.overview()["has_other_currencies"])

	def test_the_base_currency_bucket_is_listed_first(self):
		self.assertEqual(self.overview()["by_currency"][0]["currency"], "INR")

	def test_as_on_moves_every_balance_together(self):
		overview = self.overview(as_on="2026-03-01")
		balances = {a["account_name"]: a["balance"] for a in overview["accounts"]}

		self.assertEqual(balances["Ovw Savings"], 100000)
		self.assertEqual(balances["Ovw Card"], 0)
		self.assertEqual(overview["liabilities"], 0)


class TestGetCashflow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("cf-alice@example.com")
		cls.bob = make_user("cf-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.savings = make_account("CF Savings")
			cls.card = make_account("CF Card", account_type="Credit Card")
			cls.transfer_category = make_category("CF Moved", category_type="Transfer")

			make_transaction(cls.savings, "2026-04-05", "In", 85000, "CF salary")
			make_transaction(cls.savings, "2026-04-06", "Out", 250, "CF coffee")
			make_transaction(cls.card, "2026-04-07", "Out", 4200, "CF groceries")
			# Money that never left the household, expressed both ways the app allows.
			make_transaction(
				cls.savings, "2026-04-08", "Out", 10000, "CF card payment", category=cls.transfer_category
			)
			make_transaction(cls.card, "2026-04-08", "In", 10000, "CF card receipt", is_transfer=1)
			# Outside the window.
			make_transaction(cls.savings, "2026-03-31", "Out", 777, "CF march")
			make_transaction(cls.savings, "2026-05-01", "Out", 888, "CF may")

		with set_user(cls.bob):
			cls.bob_account = make_account("CF Bob Canary")
			make_transaction(cls.bob_account, "2026-04-05", "In", 999999, "CF bob secret")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def cashflow(self, **kwargs):
		with set_user(self.alice):
			return get_cashflow(from_date="2026-04-01", to_date="2026-04-30", **kwargs)

	def test_money_in_and_out_are_summed_over_the_window(self):
		result = self.cashflow()

		self.assertEqual(result["money_in"], 85000)
		self.assertEqual(result["money_out"], 4450)
		self.assertEqual(result["net"], 80550)

	def test_a_row_flagged_as_a_transfer_is_excluded(self):
		"""Moving money between your own accounts is not income and not spending; counting
		it would show a month where you earned and spent ten thousand rupees you never
		touched."""
		self.assertNotIn(10000, (self.cashflow()["money_in"], self.cashflow()["money_out"]))

	def test_a_row_in_a_transfer_category_is_excluded_too(self):
		"""Both routes have to work: the flag is set by the importer, the category by a
		rule or by hand."""
		self.assertEqual(self.cashflow()["money_out"], 4450)

	def test_the_window_boundaries_are_inclusive_and_nothing_outside_leaks_in(self):
		result = self.cashflow()

		self.assertNotIn(777, (result["money_out"], result["money_in"]))
		self.assertEqual(result["money_out"], 4450)

	def test_it_can_be_narrowed_to_one_account(self):
		result = self.cashflow(account=self.card)

		self.assertEqual(result["money_out"], 4200)
		self.assertEqual(result["money_in"], 0)

	def test_another_holders_transactions_never_count(self):
		self.assertEqual(self.cashflow()["money_in"], 85000)

	def test_the_dates_are_echoed_back(self):
		result = self.cashflow()

		self.assertEqual(result["from_date"], "2026-04-01")
		self.assertEqual(result["to_date"], "2026-04-30")


class TestCachedBalance(IntegrationTestCase):
	"""`cached_balance` is a display convenience: a list of accounts renders in one query.

	It is written by the same aggregate that reads, so it can only ever be *stale* - it
	can never drift by accumulation the way an incremental counter does. These tests pin
	that repair path.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("cache-alice@example.com")
		cls.bob = make_user("cache-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.savings = make_account("Cache Savings", opening_balance=1000)
			make_transaction(cls.savings, "2026-04-01", "Out", 100, "Cache spend")

		with set_user(cls.bob):
			cls.bob_account = make_account("Cache Bob", opening_balance=5000)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def cached(self, account):
		return frappe.db.get_value("Wallet Account", account, "cached_balance")

	def test_refreshing_stores_the_computed_balance_and_stamps_the_time(self):
		frappe.db.set_value("Wallet Account", self.savings, "cached_balance", -1, update_modified=False)

		with set_user(self.alice):
			returned = refresh_cached_balance(self.savings)

		self.assertEqual(returned, 900)
		self.assertEqual(self.cached(self.savings), 900)
		self.assertIsNotNone(frappe.db.get_value("Wallet Account", self.savings, "balance_last_updated"))

	def test_refreshing_nothing_is_a_no_op(self):
		"""Called with an empty account on the delete path, where there may be none."""
		self.assertEqual(refresh_cached_balance(""), 0.0)

	def test_the_rebuild_button_repairs_every_account_the_user_owns(self):
		frappe.db.set_value("Wallet Account", self.savings, "cached_balance", -1, update_modified=False)

		with set_user(self.alice):
			result = rebuild_balances()

		self.assertEqual(self.cached(self.savings), 900)
		self.assertGreaterEqual(result["rebuilt"], 1)

	def test_the_rebuild_button_does_not_reach_another_holders_accounts(self):
		"""It goes through `frappe.get_list`, so it is scoped to the session user."""
		frappe.db.set_value("Wallet Account", self.bob_account, "cached_balance", -1, update_modified=False)

		with set_user(self.alice):
			rebuild_balances()

		self.assertEqual(self.cached(self.bob_account), -1)

	def test_the_nightly_rebuild_covers_every_user(self):
		"""It runs as Administrator from the scheduler, which is the one place in this app
		where crossing the owner boundary is the point."""
		frappe.db.set_value("Wallet Account", self.savings, "cached_balance", -1, update_modified=False)
		frappe.db.set_value("Wallet Account", self.bob_account, "cached_balance", -1, update_modified=False)

		rebuild_all_balances()

		self.assertEqual(self.cached(self.savings), 900)
		self.assertEqual(self.cached(self.bob_account), 5000)
