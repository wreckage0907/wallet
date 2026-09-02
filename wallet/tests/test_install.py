# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.install`.

Seeding is per-user because Wallet Category and Wallet Categorization Rule are
owner-isolated - "the default categories" only exist relative to a holder. It is not a
fixture because `sync_fixtures` re-imports on every `bench migrate`, so a category you
deleted would come back and a category you renamed would be reverted.

Idempotence is therefore the property that matters, and it has two halves that are easy to
confuse: a default the user *renamed* must be recognised as still present (matched by
`default_key`), and a name the user created *by hand* must not be collided with (matched
by `category_name`).

`as_user` gets its own class. It swaps the session so inserted documents are owned by the
right person, and `frappe.set_user` clobbers more of the session than its name suggests -
inside a web request that would log the caller out on their very next request.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.install import (
	WALLET_ROLE,
	as_user,
	create_wallet_roles,
	get_wallet_users,
	seed_user_defaults,
)
from wallet.setup.default_data import DEFAULT_CATEGORIES, DEFAULT_RULES
from wallet.tests.fixtures import commit, make_user, purge


class TestCreateWalletRoles(IntegrationTestCase):
	def test_the_wallet_user_role_exists(self):
		"""It must exist before doctype sync, since every wallet doctype's permissions
		reference it - which is why it is created in `before_install`."""
		create_wallet_roles()

		self.assertTrue(frappe.db.exists("Role", WALLET_ROLE))

	def test_creating_it_again_is_a_no_op(self):
		create_wallet_roles()
		before = frappe.db.get_value("Role", WALLET_ROLE, "modified")

		create_wallet_roles()

		self.assertEqual(frappe.db.get_value("Role", WALLET_ROLE, "modified"), before)

	def test_it_has_desk_access(self):
		"""Without it the holder cannot reach the desk workspace at all."""
		create_wallet_roles()

		self.assertEqual(frappe.db.get_value("Role", WALLET_ROLE, "desk_access"), 1)


class TestGetWalletUsers(IntegrationTestCase):
	def test_the_frameworks_own_accounts_are_excluded(self):
		"""Administrator and Guest are not people with money."""
		users = get_wallet_users()

		self.assertNotIn("Administrator", users)
		self.assertNotIn("Guest", users)

	def test_a_real_system_user_is_included(self):
		user = make_user("install-listed@example.com")
		commit()

		self.assertIn(user, get_wallet_users())

	def test_a_disabled_user_is_excluded(self):
		user = make_user("install-disabled@example.com")
		frappe.db.set_value("User", user, "enabled", 0)
		commit()
		try:
			self.assertNotIn(user, get_wallet_users())
		finally:
			frappe.db.set_value("User", user, "enabled", 1)
			commit()


class TestAsUser(IntegrationTestCase):
	def test_documents_inserted_inside_are_owned_by_that_user(self):
		"""The whole reason it exists: `Document.set_user_and_timestamp` stamps `owner`
		from the session, so anything we assign by hand is overwritten."""
		user = make_user("install-owner@example.com")
		purge(user)

		with as_user(user):
			name = (
				frappe.get_doc(
					{
						"doctype": "Wallet Category",
						"category_name": "As User Test",
						"category_type": "Expense",
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		commit()

		try:
			self.assertEqual(frappe.db.get_value("Wallet Category", name, "owner"), user)
		finally:
			purge(user)
			commit()

	def test_the_session_user_is_restored_afterwards(self):
		user = make_user("install-restore@example.com")
		before = frappe.session.user

		with as_user(user):
			self.assertEqual(frappe.session.user, user)

		self.assertEqual(frappe.session.user, before)

	def test_the_rest_of_the_session_is_restored_too(self):
		"""`frappe.set_user` also replaces `session.sid`, `session.data` and `form_dict`.
		Inside a web request Frappe persists the session at the end, so a caller who hit
		`ensure_setup` would be handed a session with empty data and be logged out on their
		very next request. Swapping the user back is not enough."""
		user = make_user("install-session@example.com")
		session = frappe.local.session
		session.data = frappe._dict({"marker": "still here"})
		session.sid = "original-sid"
		frappe.local.form_dict = frappe._dict({"cmd": "something"})

		with as_user(user):
			pass

		self.assertEqual(session.data.get("marker"), "still here")
		self.assertEqual(session.sid, "original-sid")
		self.assertEqual(frappe.local.form_dict.get("cmd"), "something")

	def test_the_session_is_restored_even_when_the_block_raises(self):
		user = make_user("install-raises@example.com")
		before = frappe.session.user

		with self.assertRaises(ValueError), as_user(user):
			raise ValueError("boom")

		self.assertEqual(frappe.session.user, before)


class TestSeedUserDefaults(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("install-seed@example.com")
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

	def categories(self) -> list[str]:
		return frappe.get_all("Wallet Category", filters={"owner": self.user}, pluck="category_name")

	def test_a_fresh_holder_gets_the_whole_default_tree(self):
		result = seed_user_defaults(self.user)

		expected = sum(
			1 + len(children) for groups in DEFAULT_CATEGORIES.values() for _, _, children in groups
		)
		self.assertEqual(result["categories"], expected)

	def test_the_groups_are_groups_and_the_children_hang_off_them(self):
		seed_user_defaults(self.user)

		group_name = DEFAULT_CATEGORIES["Expense"][0][0]
		child_name = DEFAULT_CATEGORIES["Expense"][0][2][0]
		group = frappe.db.get_value(
			"Wallet Category",
			{"category_name": group_name, "owner": self.user},
			["name", "is_group"],
			as_dict=True,
		)
		child_parent = frappe.db.get_value(
			"Wallet Category", {"category_name": child_name, "owner": self.user}, "parent_wallet_category"
		)

		self.assertEqual(group.is_group, 1)
		self.assertEqual(child_parent, group.name)

	def test_the_default_rules_are_seeded_too(self):
		result = seed_user_defaults(self.user)

		self.assertEqual(result["rules"], len(DEFAULT_RULES))

	def test_seeding_twice_creates_nothing_the_second_time(self):
		seed_user_defaults(self.user)

		again = seed_user_defaults(self.user)

		self.assertEqual(again, {"categories": 0, "rules": 0})

	def test_a_renamed_default_is_not_resurrected(self):
		"""Matched by `default_key`, so the category you renamed stays renamed. Matching on
		the display name alone would give you back the original beside your rename."""
		seed_user_defaults(self.user)
		group_name = DEFAULT_CATEGORIES["Expense"][0][0]
		renamed = frappe.db.get_value("Wallet Category", {"category_name": group_name, "owner": self.user})
		frappe.db.set_value("Wallet Category", renamed, "category_name", "My Own Name")
		commit()

		seed_user_defaults(self.user)

		self.assertNotIn(group_name, self.categories())
		self.assertIn("My Own Name", self.categories())

	def test_a_deleted_default_is_restored(self):
		"""The other half of idempotence, and what `restore_default_categories` is for."""
		seed_user_defaults(self.user)
		child_name = DEFAULT_CATEGORIES["Expense"][0][2][0]
		frappe.db.delete("Wallet Categorization Rule", {"owner": self.user})
		frappe.db.delete("Wallet Category", {"category_name": child_name, "owner": self.user})
		commit()
		self.assertNotIn(child_name, self.categories())

		seed_user_defaults(self.user)

		self.assertIn(child_name, self.categories())

	def test_a_hand_made_category_of_the_same_name_is_not_collided_with(self):
		"""The second gate. Without it a restore would try to insert a duplicate name and
		be refused by the controller's per-owner uniqueness check."""
		group_name = DEFAULT_CATEGORIES["Expense"][0][0]
		with as_user(self.user):
			frappe.get_doc(
				{
					"doctype": "Wallet Category",
					"category_name": group_name,
					"category_type": "Expense",
					"is_group": 1,
				}
			).insert(ignore_permissions=True)
		commit()

		seed_user_defaults(self.user)

		self.assertEqual(self.categories().count(group_name), 1)

	def test_a_rule_whose_category_was_renamed_away_is_skipped(self):
		"""A rule's category is a reqd Link, and `seed_rules` finds it by display name.

		Renamed rather than deleted, because a *deleted* default category is restored by
		`seed_categories` on the very same call - so the only way the lookup comes back
		empty is a rename, which `default_key` deliberately lets stand. Skipping is the
		right answer: recreating the category under its old name, purely so a rule has
		somewhere to point, would undo the holder's rename.
		"""
		seed_user_defaults(self.user)
		rule_name, _, category_name, _, _ = DEFAULT_RULES[0]
		renamed = frappe.db.get_value("Wallet Category", {"category_name": category_name, "owner": self.user})
		frappe.db.delete("Wallet Categorization Rule", {"owner": self.user})
		frappe.db.set_value("Wallet Category", renamed, "category_name", "Renamed By Hand")
		commit()

		result = seed_user_defaults(self.user)

		self.assertNotIn(
			rule_name,
			frappe.get_all("Wallet Categorization Rule", filters={"owner": self.user}, pluck="rule_name"),
		)
		self.assertLess(result["rules"], len(DEFAULT_RULES))

	def test_seeding_a_user_that_does_not_exist_does_nothing(self):
		"""Rather than throwing: it is called from a hook and from a lazy safety net, and
		neither has anything useful to do with the exception."""
		self.assertEqual(seed_user_defaults("nobody@example.com"), {"categories": 0, "rules": 0})

	def test_seeded_records_belong_to_the_holder_not_the_caller(self):
		"""`ensure_setup` runs inside the holder's own request, but `after_install` runs as
		Administrator over every user."""
		seed_user_defaults(self.user)

		owners = set(frappe.get_all("Wallet Category", filters={"owner": self.user}, pluck="owner"))
		self.assertEqual(owners, {self.user})


class TestSeedUserDefaultsIsolation(IntegrationTestCase):
	def test_two_holders_get_their_own_copies_of_the_same_names(self):
		"""Which is why Wallet Category is `autoname: hash` - "Groceries" is not one row
		shared by everyone."""
		alice = make_user("install-iso-alice@example.com")
		bob = make_user("install-iso-bob@example.com")
		purge(alice, bob)
		commit()

		try:
			seed_user_defaults(alice)
			seed_user_defaults(bob)
			commit()

			group_name = DEFAULT_CATEGORIES["Expense"][0][0]
			alice_row = frappe.db.get_value("Wallet Category", {"category_name": group_name, "owner": alice})
			bob_row = frappe.db.get_value("Wallet Category", {"category_name": group_name, "owner": bob})

			self.assertTrue(alice_row)
			self.assertTrue(bob_row)
			self.assertNotEqual(alice_row, bob_row)

			with set_user(alice):
				visible = frappe.get_list("Wallet Category", filters={"name": bob_row})
			self.assertEqual(visible, [])
		finally:
			purge(alice, bob)
			commit()
