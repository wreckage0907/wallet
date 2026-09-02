# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Categorization Rule controller.

Validation only - what the rule *does* is `wallet/categorization.py`, tested separately.

Both checks exist to stop a rule that would fail silently later. An invalid regex is
caught at save time here because `categorize` deliberately swallows `re.error` at match
time: one bad pattern must not take categorization down for every other rule, which also
means a bad pattern saved anyway would quietly never match and never say so.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.tests.fixtures import commit, make_category, make_rule, make_user, purge


class TestWalletCategorizationRule(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("rule-holder@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.category = make_category("Rule Food")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	# --- pattern ----------------------------------------------------------------------

	def test_an_invalid_regex_is_refused_at_save_time(self):
		"""`categorize` swallows `re.error` at match time so one bad rule cannot break the
		rest, which means a rule saved with a bad pattern would never match and never
		complain. Catching it here is the only place the holder finds out."""
		with set_user(self.user), self.assertRaises(frappe.ValidationError):
			make_rule("Rule Broken", "[unclosed", self.category, match_type="Regex")

	def test_a_valid_regex_saves(self):
		with set_user(self.user):
			name = make_rule("Rule Valid", r"SWIGGY|ZOMATO", self.category, match_type="Regex")

		self.assertTrue(frappe.db.exists("Wallet Categorization Rule", name))

	def test_a_non_regex_pattern_is_not_compiled(self):
		""" "Contains" is a substring match, so a pattern full of regex metacharacters is
		ordinary text and must not be rejected."""
		with set_user(self.user):
			name = make_rule("Rule Literal", "AMOUNT (INR) [NET]", self.category, match_type="Contains")

		self.assertTrue(frappe.db.exists("Wallet Categorization Rule", name))

	# --- amount range -----------------------------------------------------------------

	def test_a_minimum_above_the_maximum_is_refused(self):
		"""It would match nothing, silently, forever."""
		with set_user(self.user), self.assertRaises(frappe.ValidationError):
			make_rule("Rule Bad Range", "SWIGGY", self.category, amount_min=500, amount_max=100)

	def test_a_sensible_range_saves(self):
		with set_user(self.user):
			name = make_rule("Rule Good Range", "SWIGGY", self.category, amount_min=100, amount_max=500)

		self.assertTrue(frappe.db.exists("Wallet Categorization Rule", name))

	def test_an_equal_minimum_and_maximum_is_allowed(self):
		"""An exact-amount rule - a fixed monthly EMI, say - is a real thing to want."""
		with set_user(self.user):
			name = make_rule("Rule Exact", "EMI", self.category, amount_min=32000, amount_max=32000)

		self.assertTrue(frappe.db.exists("Wallet Categorization Rule", name))

	def test_a_half_open_range_is_allowed(self):
		with set_user(self.user):
			only_min = make_rule("Rule Min Only", "SWIGGY", self.category, amount_min=100)
			only_max = make_rule("Rule Max Only", "SWIGGY", self.category, amount_max=500)

		self.assertTrue(frappe.db.exists("Wallet Categorization Rule", only_min))
		self.assertTrue(frappe.db.exists("Wallet Categorization Rule", only_max))
