# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.api.setup`.

Two endpoints, both thin wrappers over `seed_user_defaults` - which has its own suite in
`wallet/tests/test_install.py`. What is this module's own is the guard clauses and the
reporting, so that is what is tested here.

`ensure_setup` is the lazy safety net for holders who existed before the app was installed
and for any case where the `User.after_insert` hook did not fire. It has to be cheap on
every PWA boot, which is why it checks for one category before doing anything.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.api.setup import ensure_setup, restore_default_categories
from wallet.setup.default_data import DEFAULT_CATEGORIES
from wallet.tests.fixtures import commit, make_user, purge


class TestEnsureSetup(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("setup-holder@example.com")
		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def setUp(self):
		purge(self.user)
		commit()
		super().setUp()

	def test_a_holder_with_nothing_gets_seeded(self):
		with set_user(self.user):
			result = ensure_setup()

		self.assertTrue(result["seeded"])
		self.assertGreater(result["categories"], 0)

	def test_a_holder_who_already_has_categories_is_left_alone(self):
		"""It runs on every PWA boot, so the common case must be one existence check and
		nothing else."""
		with set_user(self.user):
			ensure_setup()
			result = ensure_setup()

		self.assertFalse(result["seeded"])
		self.assertEqual(result["categories"], 0)

	def test_the_seeded_records_belong_to_the_caller(self):
		with set_user(self.user):
			ensure_setup()

		owners = set(frappe.get_all("Wallet Category", filters={"owner": self.user}, pluck="owner"))
		self.assertEqual(owners, {self.user})

	def test_a_guest_is_refused(self):
		with set_user("Guest"), self.assertRaises(frappe.PermissionError):
			ensure_setup()

	def test_the_caller_is_still_logged_in_afterwards(self):
		"""Seeding runs inside `frappe.set_user`, which clobbers the session. Inside a real
		request that would log the caller out on their very next one - this endpoint is the
		reason `as_user` restores the session in full."""
		with set_user(self.user):
			session = frappe.local.session
			session.data = frappe._dict({"marker": "still here"})

			ensure_setup()

			self.assertEqual(frappe.session.user, self.user)
			self.assertEqual(session.data.get("marker"), "still here")


class TestRestoreDefaultCategories(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("setup-restore@example.com")
		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def setUp(self):
		purge(self.user)
		with set_user(self.user):
			ensure_setup()
		commit()
		super().setUp()

	def categories(self) -> list[str]:
		return frappe.get_all("Wallet Category", filters={"owner": self.user}, pluck="category_name")

	def test_a_deleted_default_comes_back(self):
		child_name = DEFAULT_CATEGORIES["Expense"][0][2][0]
		frappe.db.delete("Wallet Categorization Rule", {"owner": self.user})
		frappe.db.delete("Wallet Category", {"category_name": child_name, "owner": self.user})
		commit()

		with set_user(self.user):
			result = restore_default_categories()

		self.assertIn(child_name, self.categories())
		self.assertGreaterEqual(result["restored"], 1)

	def test_nothing_missing_means_nothing_restored(self):
		"""Non-destructive: anything still present is left exactly as it is."""
		with set_user(self.user):
			result = restore_default_categories()

		self.assertEqual(result["restored"], 0)

	def test_a_renamed_default_is_not_reverted(self):
		"""The holder's rename is a decision. Restoring is for what is missing, not for
		putting the shipped names back."""
		group_name = DEFAULT_CATEGORIES["Expense"][0][0]
		renamed = frappe.db.get_value("Wallet Category", {"category_name": group_name, "owner": self.user})
		frappe.db.set_value("Wallet Category", renamed, "category_name", "My Own Name")
		commit()

		with set_user(self.user):
			restore_default_categories()

		self.assertIn("My Own Name", self.categories())
		self.assertNotIn(group_name, self.categories())

	def test_a_guest_is_refused(self):
		with set_user("Guest"), self.assertRaises(frappe.PermissionError):
			restore_default_categories()

	def test_it_does_not_reach_another_holders_categories(self):
		other = make_user("setup-restore-other@example.com")
		purge(other)
		commit()

		try:
			with set_user(self.user):
				restore_default_categories()

			self.assertEqual(frappe.get_all("Wallet Category", filters={"owner": other}, pluck="name"), [])
		finally:
			purge(other)
			commit()
