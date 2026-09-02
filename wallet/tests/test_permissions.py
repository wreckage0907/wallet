# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.permissions`.

The invariant the whole app rests on: one holder's money never appears in another's
session. It is enforced in three places - `if_owner` on the role, the query conditions
here, and `has_permission` here - and this suite covers the two that are code.

Two decisions get a test each because both look like mistakes until you know why:

* **System Manager is not exempt.** The usual Frappe habit is to exempt it, and that is
  wrong for a finance app: System Manager is an ordinary role the account holder almost
  always has themselves, so exempting it would mean your own list views quietly mix in
  other people's transactions.
* **Wallet Bank and Wallet Statement Format are deliberately not isolated.** They hold no
  personal data, and sharing them is what makes the second person to import an HDFC
  statement get the column mapping for free.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.permissions import OWNED_DOCTYPES, get_permission_query_conditions, has_permission
from wallet.tests.fixtures import (
	commit,
	make_account,
	make_category,
	make_transaction,
	make_user,
	purge,
)


class TestPermissionQueryConditions(IntegrationTestCase):
	def test_a_condition_scopes_the_query_to_the_user(self):
		condition = get_permission_query_conditions("holder@example.com", doctype="Wallet Transaction")

		self.assertIn("`tabWallet Transaction`.`owner`", condition)
		self.assertIn("holder@example.com", condition)

	def test_the_user_is_escaped_into_the_condition(self):
		"""It is interpolated into SQL, so `frappe.db.escape` is the only thing between a
		user id and an injection. Emails are validated on the User doctype, but this
		function's contract should not depend on that."""
		condition = get_permission_query_conditions("o'brien@example.com", doctype="Wallet Account")

		self.assertNotIn("o'brien@example.com'", condition.replace("\\'", ""))
		self.assertIn("\\'", condition)

	def test_administrator_gets_no_condition(self):
		"""The break-glass account for recovery and debugging, and the only exemption."""
		self.assertEqual(get_permission_query_conditions("Administrator", doctype="Wallet Transaction"), "")

	def test_a_missing_doctype_yields_no_condition(self):
		"""The framework calls this for every doctype it filters; without a doctype there
		is no table name to qualify, and a malformed condition would break the query."""
		self.assertEqual(get_permission_query_conditions("holder@example.com"), "")

	def test_the_session_user_is_used_when_none_is_passed(self):
		user = make_user("perm-session@example.com")

		with set_user(user):
			condition = get_permission_query_conditions(doctype="Wallet Account")

		self.assertIn(user, condition)

	def test_every_personal_doctype_is_covered(self):
		"""The list here and the hooks that consume it are the whole enforcement surface,
		so a doctype added to one and not the other is a silent leak."""
		from wallet import hooks

		self.assertEqual(set(hooks.permission_query_conditions), set(OWNED_DOCTYPES))
		self.assertEqual(set(hooks.has_permission), set(OWNED_DOCTYPES))

	def test_shared_reference_data_is_deliberately_absent(self):
		"""A bank and a column mapping hold no personal data, and sharing them is the
		point - see the module docstring."""
		self.assertNotIn("Wallet Bank", OWNED_DOCTYPES)
		self.assertNotIn("Wallet Statement Format", OWNED_DOCTYPES)


class TestHasPermission(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("perm-alice@example.com")
		cls.bob = make_user("perm-bob@example.com")
		cls.manager = make_user("perm-manager@example.com", roles=("Wallet User", "System Manager"))
		purge(cls.alice, cls.bob, cls.manager)

		with set_user(cls.alice):
			cls.account = make_account("Perm Savings", opening_balance=1000)
			cls.category = make_category("Perm Groceries")
			cls.transaction = make_transaction(cls.account, "2026-04-01", "Out", 250, "Perm coffee")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob, cls.manager)
		commit()
		super().tearDownClass()

	def doc(self):
		return frappe.get_doc("Wallet Account", self.account)

	def test_a_holder_may_touch_their_own_record(self):
		self.assertTrue(has_permission(self.doc(), user=self.alice))

	def test_a_holder_may_not_touch_someone_elses(self):
		self.assertFalse(has_permission(self.doc(), user=self.bob))

	def test_a_system_manager_is_not_exempt(self):
		"""Deliberate, and the opposite of the usual Frappe habit. A System Manager is an
		ordinary role the account holder themselves almost always has."""
		self.assertFalse(has_permission(self.doc(), user=self.manager))

	def test_administrator_is_exempt(self):
		self.assertTrue(has_permission(self.doc(), user="Administrator"))

	def test_the_session_user_is_used_when_none_is_passed(self):
		with set_user(self.bob):
			self.assertFalse(has_permission(self.doc()))
		with set_user(self.alice):
			self.assertTrue(has_permission(self.doc()))


class TestIsolationEndToEnd(IntegrationTestCase):
	"""The conditions above, exercised through the framework rather than called directly.

	This is what actually protects a list view, and it is worth asserting separately: the
	function can be perfectly correct and still not be wired up.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("iso-alice@example.com")
		cls.bob = make_user("iso-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.alice_account = make_account("Iso Alice Savings")
			make_transaction(cls.alice_account, "2026-04-01", "Out", 250, "Iso alice coffee")
		with set_user(cls.bob):
			cls.bob_account = make_account("Iso Bob Savings")
			make_transaction(cls.bob_account, "2026-04-01", "Out", 999999, "Iso bob secret")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def test_a_list_shows_only_the_holders_own_accounts(self):
		with set_user(self.alice):
			names = frappe.get_list("Wallet Account", pluck="account_name", limit_page_length=0)

		self.assertIn("Iso Alice Savings", names)
		self.assertNotIn("Iso Bob Savings", names)

	def test_a_list_shows_only_the_holders_own_transactions(self):
		with set_user(self.alice):
			descriptions = frappe.get_list("Wallet Transaction", pluck="description", limit_page_length=0)

		self.assertNotIn("Iso bob secret", descriptions)

	def test_get_all_bypasses_the_conditions_entirely(self):
		"""Pinned on purpose. This is the single most likely security bug in the app, and
		a test that states it is worth more than the comment in permissions.py alone: any
		aggregate in wallet/api/ must use `frappe.get_list`, or carry its own owner filter.
		"""
		with set_user(self.alice):
			descriptions = frappe.get_all("Wallet Transaction", pluck="description")

		self.assertIn("Iso bob secret", descriptions)

	def test_a_holder_cannot_open_another_holders_document(self):
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Wallet Account", self.bob_account).check_permission("read")

	def test_shared_reference_data_is_visible_to_everyone(self):
		from wallet.tests.fixtures import make_bank

		bank = make_bank("Iso Shared Bank")
		commit()

		with set_user(self.alice):
			self.assertTrue(frappe.get_list("Wallet Bank", filters={"name": bank}))
		with set_user(self.bob):
			self.assertTrue(frappe.get_list("Wallet Bank", filters={"name": bank}))
