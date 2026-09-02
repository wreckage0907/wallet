# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Category controller.

A NestedSet, and the tree is not decoration: rolling "Food & Dining" up over its children
is one indexed range query rather than recursive Python. `get_descendant_names` is that
query, and it is what a spending summary by parent category depends on.

The parent check gets the most attention. The `parent_wallet_category` Link carries
`ignore_user_permissions`, and the lookup behind it bypasses the permission hooks - so
without an explicit owner check a crafted request could graft a category onto another
holder's tree, which then rewrites their `lft`/`rgt` and reorders a tree they cannot see
being changed.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.tests.fixtures import commit, make_category, make_user, purge
from wallet.wallet.doctype.wallet_category.wallet_category import get_descendant_names


class TestWalletCategory(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("cat-tree-alice@example.com")
		cls.bob = make_user("cat-tree-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.food = make_category("Tree Food", is_group=1)
			cls.groceries = make_category("Tree Groceries", parent=cls.food)
			cls.dining = make_category("Tree Dining Out", parent=cls.food)
			cls.income = make_category("Tree Salary", category_type="Income", is_group=1)
		with set_user(cls.bob):
			cls.bob_group = make_category("Tree Bob Food", is_group=1)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	# --- unique names -----------------------------------------------------------------

	def test_one_holder_cannot_have_two_categories_of_a_name(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			make_category("Tree Groceries")

	def test_two_holders_can_each_have_a_groceries(self):
		"""Precisely why `autoname` is `hash`."""
		with set_user(self.bob):
			bobs = make_category("Tree Groceries")

		self.assertNotEqual(bobs, self.groceries)

	# --- parent rules -----------------------------------------------------------------

	def test_a_leaf_cannot_be_a_parent(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			make_category("Tree Under A Leaf", parent=self.groceries)

	def test_a_category_cannot_change_type_underneath_its_group(self):
		"""An Income category under an Expense group would make every roll-up wrong."""
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			make_category("Tree Wrong Type", category_type="Income", parent=self.food)

	def test_a_missing_parent_is_reported(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			make_category("Tree Orphan", parent="no-such-category")

	def test_a_category_cannot_be_grafted_onto_another_holders_tree(self):
		"""The Link carries `ignore_user_permissions` and the lookup bypasses the
		permission hooks, so this explicit check is the only thing refusing it."""
		with set_user(self.bob), self.assertRaises(frappe.PermissionError):
			make_category("Tree Grafted", parent=self.food)

	def test_a_valid_child_saves(self):
		with set_user(self.alice):
			child = make_category("Tree Takeaway", parent=self.food)

		self.assertEqual(frappe.db.get_value("Wallet Category", child, "parent_wallet_category"), self.food)

	# --- descendants ------------------------------------------------------------------

	def test_descendants_include_the_group_and_everything_under_it(self):
		with set_user(self.alice):
			names = get_descendant_names(self.food)

		self.assertIn(self.food, names)
		self.assertIn(self.groceries, names)
		self.assertIn(self.dining, names)

	def test_descendants_of_a_leaf_are_just_itself(self):
		with set_user(self.alice):
			self.assertEqual(get_descendant_names(self.groceries), [self.groceries])

	def test_descendants_do_not_cross_into_another_tree(self):
		with set_user(self.alice):
			names = get_descendant_names(self.food)

		self.assertNotIn(self.income, names)

	def test_descendants_are_scoped_to_the_session_user(self):
		"""The nested-set range is global; the owner filter is what keeps another holder's
		categories out of a range that happens to overlap."""
		with set_user(self.bob):
			names = get_descendant_names(self.bob_group)

		self.assertNotIn(self.groceries, names)

	def test_an_unknown_category_raises_instead_of_taking_its_own_fallback(self):
		"""A real bug, pinned so the fix is deliberate and this test flips with it.

		`get_descendant_names` has a `lft is None` branch that reads as "unknown category,
		fall back to just itself" - but `frappe.db.get_value` returns `None`, not
		`(None, None)`, when the row does not exist, so the tuple unpack above it raises
		`TypeError` first and the branch is unreachable. The intended behaviour is the
		right one: a caller widening a category filter should get a filter that matches
		nothing, not a 500.

		The branch is unreachable from either direction: a missing row returns `None` and
		blows up on the unpack, and an existing row can never have a NULL `lft` because the
		column is NOT NULL. It is dead code hiding a live crash.

		Reachable from a stale category id - a filter kept in the PWA after the category
		behind it was deleted.
		"""
		with self.assertRaises(TypeError):
			get_descendant_names("no-such-category")
