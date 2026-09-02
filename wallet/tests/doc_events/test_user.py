# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the `User` document events this app attaches in `hooks.py`.

Under `doc_events/` rather than beside a controller because `User` is not a doctype we
own - see `specs/testing.md`. The file is named for the doctype the hook fires on.

One hook: `after_insert` gives every new system user their own default categories and
rules. It is the reason a holder who signs up after the app was installed gets the same
starting point as one who was already there.
"""

import frappe
from frappe.tests import IntegrationTestCase

from wallet.install import seed_user_defaults_for_new_user
from wallet.setup.default_data import DEFAULT_CATEGORIES
from wallet.tests.fixtures import commit, delete_user, make_user, purge


class TestSeedUserDefaultsForNewUser(IntegrationTestCase):
	def categories(self, user: str) -> list[str]:
		return frappe.get_all("Wallet Category", filters={"owner": user}, pluck="category_name")

	def test_the_hook_is_registered(self):
		"""The function can be correct and simply never called."""
		from wallet import hooks

		self.assertEqual(
			hooks.doc_events["User"]["after_insert"],
			"wallet.install.seed_user_defaults_for_new_user",
		)

	def test_creating_a_user_seeds_their_defaults(self):
		"""End to end through the framework, not by calling the hook: what is being tested
		is that a new holder ends up with a usable app."""
		email = "hook-new@example.com"
		delete_user(email)
		commit()

		user = make_user(email)
		commit()

		try:
			self.assertIn(DEFAULT_CATEGORIES["Expense"][0][0], self.categories(user))
		finally:
			delete_user(user)
			commit()

	def test_the_seeded_records_belong_to_the_new_user(self):
		email = "hook-owner@example.com"
		delete_user(email)
		commit()

		user = make_user(email)
		commit()

		try:
			owners = set(frappe.get_all("Wallet Category", filters={"owner": user}, pluck="owner"))
			self.assertEqual(owners, {user})
		finally:
			delete_user(user)
			commit()

	def test_a_website_user_is_skipped(self):
		"""Only system users get a desk and a PWA. Seeding a website user would leave a
		hundred rows nobody can reach."""
		doc = frappe._dict({"user_type": "Website User", "name": "hook-website@example.com"})

		seed_user_defaults_for_new_user(doc)

		self.assertEqual(self.categories(doc.name), [])

	def test_the_frameworks_own_accounts_are_skipped(self):
		"""Administrator and Guest are not people with money."""
		for name in ("Administrator", "Guest"):
			with self.subTest(name=name):
				before = len(self.categories(name))

				seed_user_defaults_for_new_user(frappe._dict({"user_type": "System User", "name": name}))

				self.assertEqual(len(self.categories(name)), before)
