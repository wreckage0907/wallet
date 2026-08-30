# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the MCP tool bodies.

The tools are called directly rather than over HTTP: the transport is `frappe-mcp`'s
concern, and what can actually break here is the app's own logic - isolation, name
resolution, and the validation paths.

Isolation gets the most coverage on purpose. Every tool runs as whoever holds the OAuth
token, so a query that bypasses `permission_query_conditions` would quietly expose one
user's finances to another. That is the failure this suite exists to catch.
"""

import frappe
from frappe.tests import IntegrationTestCase, change_settings, set_user

from wallet.mcp import resolve, tools


class TestMCPTools(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("mcp-alice@example.com")
		cls.bob = make_user("mcp-bob@example.com")

		# This suite runs against a real dev database, so it owns its fixtures end to end:
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.alice_account = make_account("Alice Savings")
			cls.alice_category = make_category("Alice Groceries")
			make_transaction(cls.alice_account, "2026-08-01", "Out", 250, "Alice supermarket")
			make_transaction(cls.alice_account, "2026-08-02", "In", 5000, "Alice salary")

		with set_user(cls.bob):
			cls.bob_account = make_account("Bob Current")
			make_transaction(cls.bob_account, "2026-08-01", "Out", 999, "Bob secret")
			# Deliberately matches the search term Alice's test uses. If or_filters ever
			# escaped the owner condition, this row would surface in Alice's results.
			make_transaction(cls.bob_account, "2026-08-02", "In", 4242, "Bob salary")

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		frappe.db.commit()
		super().tearDownClass()

	# --- isolation ------------------------------------------------------------------

	def test_list_accounts_shows_only_own_accounts(self):
		with set_user(self.alice):
			names = [a["name"] for a in tools.list_accounts()["accounts"]]

		self.assertIn("Alice Savings", names)
		self.assertNotIn("Bob Current", names)

	def test_list_transactions_shows_only_own_transactions(self):
		with set_user(self.alice):
			descriptions = [t["description"] for t in tools.list_transactions()["transactions"]]

		self.assertIn("Alice supermarket", descriptions)
		self.assertNotIn("Bob secret", descriptions)

	def test_list_categories_shows_only_own_categories(self):
		with set_user(self.bob):
			names = [c["name"] for c in tools.list_categories()["categories"]]

		self.assertNotIn("Alice Groceries", names)

	def test_spending_summary_excludes_other_users(self):
		with set_user(self.bob):
			summary = tools.get_spending_summary("2026-08-01", "2026-08-31")

		# 999 is Bob's only spend; Alice's 250 must not appear.
		self.assertEqual(summary["money_out"], 999)

	def test_cannot_resolve_another_users_account(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			resolve.account("Bob Current")

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_cannot_write_to_another_users_account(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			tools.add_transaction("Bob Current", "2026-08-10", "Out", 10)

	# --- name resolution ------------------------------------------------------------

	def test_unknown_account_error_lists_valid_options(self):
		with set_user(self.alice):
			with self.assertRaises(frappe.ValidationError) as cm:
				resolve.account("Nonexistent Account")

		self.assertIn("Alice Savings", str(cm.exception))

	def test_account_name_is_case_insensitive(self):
		with set_user(self.alice):
			self.assertEqual(resolve.account("alice savings"), self.alice_account)

	# --- write gate -----------------------------------------------------------------

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_add_transaction_refused_when_writes_disabled(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError) as cm:
			tools.add_transaction("Alice Savings", "2026-08-20", "Out", 10)

		self.assertIn("Allow MCP Writes", str(cm.exception))

	# --- add_transaction ------------------------------------------------------------

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_returns_resulting_balance(self):
		with set_user(self.alice):
			result = tools.add_transaction(
				"Alice Savings", "2026-08-05", "Out", 100, description="Alice coffee"
			)

		self.assertTrue(result["created"])
		self.assertIn("account_balance", result)
		self.assertEqual(result["transaction"]["amount"], 100)

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_echoes_canonical_account_name(self):
		"""Echoing the caller's own string back confirms nothing - return the real name."""
		with set_user(self.alice):
			result = tools.add_transaction(
				"alice savings", "2026-08-04", "Out", 12, description="Alice canonical name"
			)

		self.assertEqual(result["transaction"]["account"], "Alice Savings")

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_accepts_lowercase_direction(self):
		with set_user(self.alice):
			result = tools.add_transaction(
				"Alice Savings", "2026-08-06", "out", 11, description="Alice lowercase"
			)

		self.assertEqual(result["transaction"]["direction"], "Out")

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_rejects_bad_direction(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			tools.add_transaction("Alice Savings", "2026-08-05", "sideways", 100)

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_rejects_negative_amount(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			tools.add_transaction("Alice Savings", "2026-08-05", "Out", -100)

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_rejects_unknown_category(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			tools.add_transaction("Alice Savings", "2026-08-05", "Out", 100, category="No Such Category")

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_add_transaction_rejects_date_before_opening(self):
		with set_user(self.alice), self.assertRaises(frappe.ValidationError):
			tools.add_transaction("Alice Savings", "2019-01-01", "Out", 100)

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_duplicate_reference_number_is_refused_by_name_not_sql_error(self):
		"""`dedup_hash` is UNIQUE, so a colliding insert must be caught before MariaDB
		raises 1062 - the model can act on "duplicates TXN-x", not on an error code."""
		with set_user(self.alice):
			first = tools.add_transaction(
				"Alice Savings",
				"2026-08-07",
				"Out",
				77,
				description="Alice UTR probe",
				reference_number="UTR-MCP-0001",
			)
			second = tools.add_transaction(
				"Alice Savings",
				"2026-08-07",
				"Out",
				77,
				description="Alice UTR probe",
				reference_number="UTR-MCP-0001",
			)

		self.assertTrue(first["created"])
		self.assertFalse(second["created"])
		self.assertEqual(second["reason"], "duplicate")
		self.assertEqual(second["duplicate_of"]["id"], first["transaction"]["id"])

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_repeat_transaction_without_reference_is_allowed(self):
		"""Two identical cash payments on one day are two real transactions.

		With no reference number and no running balance, build_dedup_hash falls back to an
		occurrence ordinal precisely so this case stays distinct - see wallet/utils/dedup.py.
		The duplicate check must not "helpfully" block it."""
		with set_user(self.alice):
			first = tools.add_transaction("Alice Savings", "2026-08-08", "Out", 60, description="Alice chai")
			second = tools.add_transaction("Alice Savings", "2026-08-08", "Out", 60, description="Alice chai")

		self.assertTrue(first["created"])
		self.assertTrue(second["created"])
		self.assertNotEqual(first["transaction"]["id"], second["transaction"]["id"])

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_failed_write_leaves_nothing_behind(self):
		with set_user(self.alice):
			before = len(tools.list_transactions(limit=200)["transactions"])
			with self.assertRaises(frappe.ValidationError):
				tools.add_transaction(
					"Alice Savings", "2019-01-01", "Out", 100, description="Alice never saved"
				)
			after = len(tools.list_transactions(limit=200)["transactions"])

		self.assertEqual(before, after)

	# --- wiring ---------------------------------------------------------------------

	def test_every_registered_tool_is_wrapped_in_the_guard(self):
		"""Without this, deleting `guarded` from registry.py breaks the production
		rollback invariant and fails no test at all."""
		from wallet.mcp import registry

		registered = {}

		class StubMCP:
			def tool(self, **kwargs):
				def decorator(fn):
					registered[fn.__name__] = fn
					return fn

				return decorator

		registry.register_tools(StubMCP())

		self.assertEqual(len(registered), len(registry.TOOLS))
		for fn, _annotations in registry.TOOLS:
			# functools.wraps keeps the name, which frappe_mcp keys its registry on - so a
			# wrapped tool is still findable, but must not be the bare function.
			self.assertIn(fn.__name__, registered)
			self.assertIsNot(registered[fn.__name__], fn)

	# --- filters --------------------------------------------------------------------

	def test_list_transactions_filters_by_direction_and_search(self):
		"""Bob has a matching "Bob salary" row, so this fails if the OR group ever escapes
		the owner condition rather than being ANDed with it."""
		with set_user(self.alice):
			result = tools.list_transactions(direction="In", search="salary")

		self.assertEqual(len(result["transactions"]), 1)
		self.assertEqual(result["transactions"][0]["description"], "Alice salary")

	def test_list_transactions_flags_truncation(self):
		with set_user(self.alice):
			page = tools.list_transactions(limit=1)
			everything = tools.list_transactions(limit=200)

		self.assertEqual(page["count"], 1)
		self.assertTrue(page["has_more"])
		self.assertFalse(everything["has_more"])

	def test_list_transactions_caps_limit(self):
		with set_user(self.alice):
			result = tools.list_transactions(limit=10_000)

		self.assertLessEqual(result["count"], tools.MAX_LIMIT)


def purge(*users: str) -> None:
	"""Remove every fixture these users own, children first.

	Run at both ends: setUpClass so a crashed run does not poison the next one,
	tearDownClass so the dev site is left as it was found. `frappe.db.delete` skips
	document hooks, which is what makes the ordering here sufficient.
	"""
	# Wallet Categorization Rule first, and it must be here at all: User.after_insert seeds
	# each user a set of rules whose `category` is a reqd Link into the categories seeded
	# alongside them. Dropping the categories without the rules leaves every rule dangling,
	# and the next fixture whose description matches one dies with LinkValidationError.
	for doctype in (
		"Wallet Transaction",
		"Wallet Categorization Rule",
		"Wallet Account",
		"Wallet Category",
	):
		for user in users:
			frappe.db.delete(doctype, {"owner": user})


def make_user(email: str) -> str:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": "Wallet User"}],
			}
		)
		user.insert(ignore_permissions=True)

	return email


def make_account(account_name: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Account",
				"account_name": account_name,
				"account_type": "Savings",
				"currency": "INR",
				"opening_balance": 0,
				"opening_date": "2020-01-01",
			}
		)
		.insert()
		.name
	)


def make_category(category_name: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Category",
				"category_name": category_name,
				"category_type": "Expense",
			}
		)
		.insert()
		.name
	)


def make_transaction(account: str, posting_date: str, direction: str, amount: float, description: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Transaction",
				"account": account,
				"posting_date": posting_date,
				"direction": direction,
				"amount": amount,
				"description": description,
			}
		)
		.insert()
		.name
	)
