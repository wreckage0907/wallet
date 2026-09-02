# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Bank controller.

There is no controller logic - the class is a bare `Document` - so what is worth asserting
is the design decision it embodies, which no other test would catch if it were reversed:
Wallet Bank is shared reference data, deliberately not owner-isolated. It holds no
personal content, and sharing it is what lets a Wallet Statement Format saved by one
holder be reused by every other holder of the same bank.

If someone later adds Wallet Bank to `OWNED_DOCTYPES`, the format-sharing that makes a
repeat import one click stops working - and it stops working quietly, for the second
person only.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.permissions import OWNED_DOCTYPES
from wallet.tests.fixtures import commit, make_bank, make_user


class TestWalletBank(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("bank-alice@example.com")
		cls.bob = make_user("bank-bob@example.com")

		with set_user(cls.alice):
			cls.bank = make_bank("Bank Shared HDFC")

		commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("Wallet Bank", {"bank_name": ["like", "Bank Shared%"]})
		commit()
		super().tearDownClass()

	def test_a_bank_created_by_one_holder_is_visible_to_another(self):
		with set_user(self.bob):
			visible = frappe.get_list("Wallet Bank", filters={"name": self.bank}, pluck="name")

		self.assertEqual(visible, [self.bank])

	def test_it_is_deliberately_not_owner_isolated(self):
		"""Stated as a test because the alternative looks tidier and is wrong - see the
		module docstring, and `wallet/permissions.py`."""
		self.assertNotIn("Wallet Bank", OWNED_DOCTYPES)

	def test_it_carries_no_permission_hooks(self):
		from wallet import hooks

		self.assertNotIn("Wallet Bank", hooks.permission_query_conditions)
		self.assertNotIn("Wallet Bank", hooks.has_permission)
