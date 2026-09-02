# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.categorization`.

`categorize` is a pure function over plain dicts, but the rules it reads are rows, so the
suite is an integration one. The dicts are shaped the way the statement importer shapes
them: a staged row, before any Wallet Transaction exists.

Two properties get the most attention, because both are load-bearing and neither is
visible from a single call:

* rules are owner-scoped, and `get_rules` uses `frappe.get_all` - which bypasses
  `permission_query_conditions` entirely, so its explicit owner filter is the only thing
  standing between two holders' rule sets.
* `categorize` never writes. Counting a match while merely *previewing* an import inflated
  the tally every time a user re-parsed or abandoned a statement.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.categorization import categorize, get_rules, record_match
from wallet.tests.fixtures import commit, make_category, make_rule, make_user, purge


class TestGetRules(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("cat-alice@example.com")
		cls.bob = make_user("cat-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.groceries = make_category("Alice Groceries")
			cls.food = make_category("Alice Food")
			make_rule("Alice late", "SWIGGY", cls.food, priority=50)
			make_rule("Alice early", "SWIGGY", cls.groceries, priority=1)
			make_rule("Alice disabled", "SWIGGY", cls.food, priority=0, enabled=0)

		with set_user(cls.bob):
			cls.bob_category = make_category("Bob Groceries")
			make_rule("Bob rule", "SWIGGY", cls.bob_category, priority=0)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def test_only_the_users_own_rules_come_back(self):
		"""`get_all` ignores permission query conditions, so the explicit owner filter in
		`get_rules` is the only thing scoping this."""
		with set_user(self.alice):
			names = [rule["name"] for rule in get_rules()]

		self.assertNotIn(
			"Bob rule", [frappe.db.get_value("Wallet Categorization Rule", n, "rule_name") for n in names]
		)
		self.assertEqual(
			{frappe.db.get_value("Wallet Categorization Rule", n, "rule_name") for n in names},
			{"Alice early", "Alice late"},
		)

	def test_disabled_rules_are_left_out(self):
		with set_user(self.alice):
			titles = [
				frappe.db.get_value("Wallet Categorization Rule", rule["name"], "rule_name")
				for rule in get_rules()
			]

		self.assertNotIn("Alice disabled", titles)

	def test_rules_arrive_cheapest_to_match_first(self):
		"""Priority order is what makes "first match wins" a decision rather than an
		accident of insertion order."""
		with set_user(self.alice):
			priorities = [rule["priority"] for rule in get_rules()]

		self.assertEqual(priorities, sorted(priorities))

	def test_an_explicit_user_overrides_the_session(self):
		"""The importer passes the import's owner, not whoever is logged in."""
		with set_user(self.alice):
			names = [
				frappe.db.get_value("Wallet Categorization Rule", rule["name"], "rule_name")
				for rule in get_rules(self.bob)
			]

		self.assertEqual(names, ["Bob rule"])


class TestCategorize(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("cat-matcher@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.category = make_category("Matcher Food")
			cls.other_category = make_category("Matcher Travel")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def rule(self, **overrides) -> list[dict]:
		"""One rule as a plain dict, so match behaviour can be exercised without a row."""
		return [
			{
				"name": "R1",
				"priority": 10,
				"match_field": "description",
				"match_type": "Contains",
				"pattern": "SWIGGY",
				"direction_filter": "Any",
				"account_filter": None,
				"amount_min": None,
				"amount_max": None,
				"category": self.category,
				"set_counterparty": None,
				"set_payment_mode": None,
				**overrides,
			}
		]

	def test_contains_matches_case_insensitively(self):
		match = categorize({"description": "upi-swiggy order 12345"}, self.rule())

		self.assertEqual(match["category"], self.category)
		self.assertEqual(match["rule"], "R1")

	def test_starts_with_only_matches_at_the_beginning(self):
		rules = self.rule(match_type="Starts With", pattern="UPI")

		self.assertEqual(categorize({"description": "UPI-SWIGGY"}, rules)["category"], self.category)
		self.assertIsNone(categorize({"description": "NEFT-UPI"}, rules)["category"])

	def test_equals_demands_the_whole_string(self):
		rules = self.rule(match_type="Equals", pattern="SWIGGY")

		self.assertEqual(categorize({"description": "swiggy"}, rules)["category"], self.category)
		self.assertIsNone(categorize({"description": "UPI-SWIGGY"}, rules)["category"])

	def test_regex_matches_case_insensitively(self):
		rules = self.rule(match_type="Regex", pattern=r"SWIGGY|ZOMATO")

		self.assertEqual(categorize({"description": "upi zomato"}, rules)["category"], self.category)

	def test_a_broken_regex_fails_that_rule_alone(self):
		"""A rule saved before validation tightened, or edited straight in the database.
		One bad pattern must not take categorization down for every other rule."""
		broken = self.rule(name="broken", match_type="Regex", pattern="[unclosed")
		working = self.rule(name="working", priority=20)

		match = categorize({"description": "UPI-SWIGGY"}, broken + working)

		self.assertEqual(match["rule"], "working")

	def test_an_unknown_match_type_matches_nothing(self):
		self.assertIsNone(categorize({"description": "SWIGGY"}, self.rule(match_type="Fuzzy"))["category"])

	def test_the_direction_filter_is_honoured(self):
		rules = self.rule(direction_filter="Out")

		self.assertEqual(
			categorize({"description": "SWIGGY", "direction": "Out"}, rules)["category"], self.category
		)
		self.assertIsNone(categorize({"description": "SWIGGY", "direction": "In"}, rules)["category"])

	def test_a_direction_filter_of_any_matches_both(self):
		rules = self.rule(direction_filter="Any")

		for direction in ("In", "Out"):
			with self.subTest(direction=direction):
				self.assertEqual(
					categorize({"description": "SWIGGY", "direction": direction}, rules)["category"],
					self.category,
				)

	def test_the_account_filter_is_honoured(self):
		rules = self.rule(account_filter="acct-one")

		self.assertEqual(
			categorize({"description": "SWIGGY", "account": "acct-one"}, rules)["category"], self.category
		)
		self.assertIsNone(categorize({"description": "SWIGGY", "account": "acct-two"}, rules)["category"])

	def test_the_amount_range_is_honoured(self):
		rules = self.rule(amount_min=100, amount_max=500)

		self.assertEqual(
			categorize({"description": "SWIGGY", "amount": 250}, rules)["category"], self.category
		)
		self.assertIsNone(categorize({"description": "SWIGGY", "amount": 50}, rules)["category"])
		self.assertIsNone(categorize({"description": "SWIGGY", "amount": 900}, rules)["category"])

	def test_a_rule_can_match_on_a_field_other_than_the_description(self):
		rules = self.rule(match_field="counterparty", pattern="LANDLORD")

		self.assertEqual(
			categorize({"description": "NEFT", "counterparty": "MY LANDLORD"}, rules)["category"],
			self.category,
		)

	def test_an_empty_haystack_never_matches(self):
		"""Otherwise "Contains" against a blank narration would match every rule."""
		for txn in ({"description": None}, {"description": "   "}, {}):
			with self.subTest(txn=txn):
				self.assertIsNone(categorize(txn, self.rule())["category"])

	def test_the_first_matching_rule_wins(self):
		"""Callers hand rules in priority order, so "first" means "highest priority"."""
		first = self.rule(name="first", category=self.category)
		second = self.rule(name="second", category=self.other_category)

		self.assertEqual(categorize({"description": "SWIGGY"}, first + second)["rule"], "first")

	def test_no_match_returns_every_target_as_none(self):
		"""The importer writes these straight onto a staged row, so the shape has to be
		the same whether anything matched or not."""
		match = categorize({"description": "NOTHING HERE"}, self.rule())

		self.assertEqual(match, {"category": None, "counterparty": None, "payment_mode": None, "rule": None})

	def test_a_rule_can_set_a_counterparty_and_a_payment_mode(self):
		rules = self.rule(set_counterparty="Swiggy", set_payment_mode="UPI")

		match = categorize({"description": "UPI-SWIGGY"}, rules)

		self.assertEqual(match["counterparty"], "Swiggy")
		self.assertEqual(match["payment_mode"], "UPI")

	def test_rules_are_fetched_for_the_transaction_owner_when_none_are_passed(self):
		"""The batch path passes rules in; the single-transaction path does not."""
		with set_user(self.user):
			rule = make_rule("Owner lookup", "LANDLORD", self.category)
			commit()
			try:
				match = categorize({"description": "NEFT MY LANDLORD", "owner": self.user})
			finally:
				frappe.delete_doc("Wallet Categorization Rule", rule, force=True)
				commit()

		self.assertEqual(match["category"], self.category)


class TestRecordMatch(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("cat-counter@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.category = make_category("Counter Food")
			cls.rule = make_rule("Counter rule", "SWIGGY", cls.category)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def times_matched(self) -> int:
		return frappe.db.get_value("Wallet Categorization Rule", self.rule, "times_matched") or 0

	def test_a_match_increments_the_tally(self):
		before = self.times_matched()

		record_match(self.rule)

		self.assertEqual(self.times_matched(), before + 1)

	def test_a_brand_new_rule_counts_from_zero(self):
		"""The column is Int and NOT NULL, so it starts at 0 rather than NULL - the
		COALESCE in the update is belt and braces, and this pins the premise it rests on."""
		with set_user(self.user):
			fresh = make_rule("Counter fresh", "ZOMATO", self.category)
		commit()

		self.assertEqual(frappe.db.get_value("Wallet Categorization Rule", fresh, "times_matched"), 0)

		record_match(fresh)

		self.assertEqual(frappe.db.get_value("Wallet Categorization Rule", fresh, "times_matched"), 1)

	def test_no_rule_is_a_no_op(self):
		"""`categorize` returns rule=None when nothing matched, and that goes straight in."""
		before = self.times_matched()

		record_match(None)

		self.assertEqual(self.times_matched(), before)

	def test_categorizing_does_not_count_anything(self):
		"""The separation this function exists for: previewing an import must not inflate
		the tally, however many times the user re-parses or abandons the statement."""
		before = self.times_matched()

		with set_user(self.user):
			for _ in range(3):
				categorize({"description": "UPI-SWIGGY", "owner": self.user})

		self.assertEqual(self.times_matched(), before)
