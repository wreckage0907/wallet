# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.treeview` (audit finding 1).

The framework's tree method listed every user's Wallet Category names, because it runs a
raw query with no permission check. These tests call it the way an attacker would - by
its original whitelisted name, through the same override resolution the request handler
uses - not just the replacement the desk tree view now points at.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.tests.fixtures import commit, make_category, make_user, purge
from wallet.treeview import get_children

FRAMEWORK_METHOD = "frappe.desk.treeview.get_children"


def call_whitelisted(method: str, **kwargs):
	"""Resolve `method` the way `frappe.handler.execute_cmd` does, then call it."""
	return frappe.get_attr(frappe.override_whitelisted_method(method))(**kwargs)


def values(nodes) -> set[str]:
	return {node["value"] for node in nodes}


class TestTreeChildren(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("treeview-alice@example.com")
		cls.bob = make_user("treeview-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.alice_root = make_category("Treeview Alice Group", is_group=1)
			cls.alice_child = make_category("Treeview Alice Child", parent=cls.alice_root)
		with set_user(cls.bob):
			cls.bob_root = make_category("Treeview Bob Group", is_group=1)
			cls.bob_child = make_category("Treeview Bob Child", parent=cls.bob_root)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def test_the_framework_method_is_overridden(self):
		self.assertEqual(frappe.override_whitelisted_method(FRAMEWORK_METHOD), "wallet.treeview.get_children")

	def test_roots_are_the_callers_own(self):
		with set_user(self.alice):
			roots = values(call_whitelisted(FRAMEWORK_METHOD, doctype="Wallet Category", parent=""))

		self.assertIn(self.alice_root, roots)
		self.assertNotIn(self.bob_root, roots)

	def test_every_root_belongs_to_the_caller(self):
		"""Not just Bob's - nobody else's, including the seeded defaults of every other
		user on the site, which is what the audit measured leaking."""
		with set_user(self.alice):
			roots = call_whitelisted(FRAMEWORK_METHOD, doctype="Wallet Category", parent="")

		owners = {frappe.db.get_value("Wallet Category", node["value"], "owner") for node in roots}
		self.assertEqual(owners, {self.alice})

	def test_another_users_node_cannot_be_expanded(self):
		with set_user(self.alice):
			children = call_whitelisted(FRAMEWORK_METHOD, doctype="Wallet Category", parent=self.bob_root)

		self.assertEqual(children, [])

	def test_the_callers_own_node_expands(self):
		with set_user(self.alice):
			children = values(get_children("Wallet Category", parent=self.alice_root))

		self.assertEqual(children, {self.alice_child})

	def test_get_all_nodes_is_covered_too(self):
		"""`get_all_nodes` calls whatever `tree_method` the client names, so naming the
		framework method must still land on the override."""
		from frappe.desk.treeview import get_all_nodes

		with set_user(self.bob):
			tree = get_all_nodes("Wallet Category", "Wallet Category", "", FRAMEWORK_METHOD)

		seen = {node["value"] for level in tree for node in level["data"]}
		self.assertIn(self.bob_child, seen)
		self.assertNotIn(self.alice_root, seen)
		self.assertNotIn(self.alice_child, seen)

	def test_nodes_carry_the_category_name_as_title(self):
		with set_user(self.alice):
			nodes = get_children("Wallet Category", parent=self.alice_root)

		self.assertEqual(nodes[0]["title"], "Treeview Alice Child")
		self.assertEqual(nodes[0]["expandable"], 0)

	def test_a_doctype_outside_wallet_falls_through_to_the_framework(self):
		"""The override sits in front of every tree on the site - ERPNext's accounts and
		warehouses included - so anything that is not a Wallet doctype must reach the
		framework untouched."""
		with patch("wallet.treeview.treeview.get_children", return_value=["framework"]) as framework:
			result = get_children("Warehouse", parent="Stores", include_disabled=True, is_root=False)

		self.assertEqual(result, ["framework"])
		framework.assert_called_once_with("Warehouse", "Stores", True, is_root=False)
