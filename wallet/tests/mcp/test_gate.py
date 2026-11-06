# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for Wallet over Frappe's built-in MCP server, and the write gate.

A write over MCP needs both the site switch (`Wallet Settings.allow_mcp_writes`) and the
user's own opt-in (`User.wallet_allow_mcp_writes`). The site-switch tests opt the user in,
so the site switch is the only thing standing in the way; the opt-in tests do the reverse.

Every call here goes through `frappe.mcp.tools.call`, the built-in server's own tool
dispatch, rather than straight to a Wallet function. The generic tools are the point: an
agent never has to touch `wallet.mcp.tools` to write a Wallet document, so a gate that only
the Wallet tools honoured would cover nothing.
"""

import frappe
from frappe.tests import IntegrationTestCase, change_settings, set_user

from wallet.api import mcp_access
from wallet.mcp import gate
from wallet.setup.custom_fields import MCP_OPT_IN_FIELD
from wallet.tests.fixtures import commit, make_account, make_transaction, make_user, purge
from wallet.tests.mcp.utils import call_tool, mcp_request

TXN = "Wallet Transaction"


class TestMCPGate(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = make_user("mcp-gate-alice@example.com")
		cls.bob = make_user("mcp-gate-bob@example.com")
		purge(cls.alice, cls.bob)

		with set_user(cls.alice):
			cls.alice_account = make_account("Gate Alice Savings")
			cls.alice_txn = make_transaction(cls.alice_account, "2026-08-01", "Out", 250, "Gate Alice rent")

		with set_user(cls.bob):
			cls.bob_account = make_account("Gate Bob Current")
			cls.bob_txn = make_transaction(cls.bob_account, "2026-08-01", "Out", 999, "Gate Bob secret")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.alice, cls.bob)
		commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.opt_in(self.alice)

	def tearDown(self):
		# Explicit: IntegrationTestCase only rolls back once per class, and tearDownClass
		# commits, so an opt-in left behind here would land in the database for real.
		frappe.db.rollback()
		super().tearDown()

	@staticmethod
	def opt_in(user: str, enabled: bool = True) -> None:
		frappe.db.set_value("User", user, MCP_OPT_IN_FIELD, int(enabled))

	def new_transaction(self, description: str) -> dict:
		return {
			"account": self.alice_account,
			"posting_date": "2026-08-10",
			"direction": "Out",
			"amount": 10,
			"description": description,
		}

	# --- the framework contract the gate relies on ---------------------------------

	def test_built_in_transport_marks_the_request(self):
		"""The gate keys on `frappe.local.mcp_request`, a framework internal. If Frappe
		renames it, this fails - otherwise the gate would silently stop gating."""
		from frappe.mcp.protocol import McpError
		from frappe.mcp.transport import handle_request
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		frappe.local.mcp_request = None
		try:
			# The context is set before anything else is checked, so a GET - which the
			# transport refuses - is enough to observe it without a full JSON-RPC exchange.
			with self.assertRaises(McpError):
				handle_request(Request(EnvironBuilder(method="GET", path="/api/v2/mcp").get_environ()))

			self.assertTrue(gate.is_mcp_request())
		finally:
			frappe.local.mcp_request = None

		self.assertFalse(gate.is_mcp_request())

	# --- site switch off -----------------------------------------------------------------

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_create_document_refused(self):
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			call_tool("create_document", doctype=TXN, data=self.new_transaction("Gate create"))

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_update_document_refused(self):
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			call_tool("update_document", doctype=TXN, name=self.alice_txn, data={"description": "edited"})

		self.assertEqual(frappe.db.get_value(TXN, self.alice_txn, "description"), "Gate Alice rent")

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_delete_document_refused(self):
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			call_tool("delete_document", doctype=TXN, name=self.alice_txn)

		self.assertTrue(frappe.db.exists(TXN, self.alice_txn))

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_add_transaction_via_call_method_refused(self):
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			call_tool(
				"call_method",
				method="wallet.mcp.tools.add_transaction",
				args={
					"account": "Gate Alice Savings",
					"posting_date": "2026-08-10",
					"direction": "Out",
					"amount": 10,
				},
			)

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_raw_balance_writes_refused(self):
		"""These write with db.set_value, which skips document events, so they ask the
		gate themselves."""
		with set_user(self.alice):
			with self.assertRaises(frappe.PermissionError):
				call_tool(
					"call_document_method",
					doctype="Wallet Account",
					name=self.alice_account,
					method="refresh_cached_balance",
				)
			with self.assertRaises(frappe.PermissionError):
				call_tool("call_method", method="wallet.api.balance.rebuild_balances")

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_agent_cannot_turn_its_own_writes_on(self):
		"""Administrator, because Wallet Settings is otherwise System Manager only - the
		account for which this would matter most."""
		with self.assertRaises(frappe.PermissionError):
			call_tool(
				"update_document",
				doctype="Wallet Settings",
				name="Wallet Settings",
				data={"allow_mcp_writes": 1},
			)

		self.assertFalse(frappe.db.get_single_value("Wallet Settings", "allow_mcp_writes"))

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_writes_outside_mcp_are_unaffected(self):
		"""The PWA, desk and REST API must not notice the gate at all."""
		with set_user(self.alice):
			doc = frappe.get_doc({"doctype": TXN, **self.new_transaction("Gate outside MCP")}).insert()

		self.assertTrue(frappe.db.exists(TXN, doc.name))
		frappe.delete_doc(TXN, doc.name, force=True)

	# --- both switches on ------------------------------------------------------------------

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_create_and_delete_document_allowed(self):
		with set_user(self.alice):
			created = call_tool("create_document", doctype=TXN, data=self.new_transaction("Gate allowed"))
			self.assertEqual(created["owner"], self.alice)

			call_tool("delete_document", doctype=TXN, name=created["name"])

		self.assertFalse(frappe.db.exists(TXN, created["name"]))

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_cannot_write_another_users_document(self):
		"""The gate opens the write path, not other people's records."""
		with set_user(self.alice), self.assertRaises(frappe.PermissionError):
			call_tool("update_document", doctype=TXN, name=self.bob_txn, data={"description": "mine now"})

		self.assertEqual(frappe.db.get_value(TXN, self.bob_txn, "description"), "Gate Bob secret")

	# --- per-user opt-in ------------------------------------------------------------

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_site_switch_alone_does_not_open_writes(self):
		"""Issue #22: a user who has not opted in cannot write, whatever the site says."""
		self.opt_in(self.alice, False)

		with set_user(self.alice):
			with self.assertRaises(frappe.PermissionError) as cm:
				call_tool("create_document", doctype=TXN, data=self.new_transaction("Gate not opted in"))
			with self.assertRaises(frappe.PermissionError):
				call_tool(
					"call_method",
					method="wallet.mcp.tools.add_transaction",
					args={
						"account": "Gate Alice Savings",
						"posting_date": "2026-08-10",
						"direction": "Out",
						"amount": 10,
					},
				)

		self.assertIn("not allowed AI agents", str(cm.exception))

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_one_users_opt_in_does_not_open_anothers(self):
		self.opt_in(self.bob, False)

		with set_user(self.bob), self.assertRaises(frappe.PermissionError):
			call_tool("update_document", doctype=TXN, name=self.bob_txn, data={"description": "edited"})

	@change_settings("Wallet Settings", allow_mcp_writes=1)
	def test_agent_cannot_opt_its_user_in(self):
		self.opt_in(self.alice, False)

		with set_user(self.alice):
			with self.assertRaises(frappe.PermissionError):
				call_tool(
					"call_method", method="wallet.api.mcp_access.set_mcp_writes", args={"enabled": True}
				)
			with self.assertRaises(frappe.PermissionError):
				call_tool("update_document", doctype="User", name=self.alice, data={MCP_OPT_IN_FIELD: 1})
			with self.assertRaises(frappe.PermissionError):
				call_tool(
					"call_method",
					method="frappe.client.set_value",
					args={"doctype": "User", "name": self.alice, "fieldname": MCP_OPT_IN_FIELD, "value": 1},
				)

		self.assertFalse(gate.user_opted_in(self.alice))

	def test_user_opts_in_from_the_app(self):
		self.opt_in(self.alice, False)

		with set_user(self.alice):
			self.assertTrue(mcp_access.set_mcp_writes(True)["user"])
			self.assertTrue(gate.user_opted_in())
			self.assertFalse(mcp_access.set_mcp_writes(False)["user"])

	def test_nobody_else_can_opt_a_user_in(self):
		"""Not even Administrator: the opt-in is the user's decision."""
		self.opt_in(self.alice, False)
		user = frappe.get_doc("User", self.alice)
		user.set(MCP_OPT_IN_FIELD, 1)

		with self.assertRaises(frappe.PermissionError):
			user.save(ignore_permissions=True)

	@change_settings("Wallet Settings", allow_mcp_writes=0)
	def test_access_reports_which_switch_is_off(self):
		with set_user(self.alice):
			self.assertEqual(mcp_access.get_mcp_access(), {"site": False, "user": True, "writable": False})

	# --- the retired endpoint ---------------------------------------------------------

	def test_old_endpoint_says_where_it_moved(self):
		"""Issue #15: a client still pointed at the old URL gets a JSON-RPC error naming the
		new one, never a traceback."""
		import json

		from wallet.mcp import handle_mcp

		response = handle_mcp()

		self.assertEqual(response.status_code, 410)
		body = json.loads(response.get_data())
		self.assertEqual(body["jsonrpc"], "2.0")
		self.assertTrue(body["error"]["data"]["endpoint"].endswith("/api/v2/mcp"))

	# --- reads through the built-in server --------------------------------------------

	def test_call_method_reaches_wallet_tools_with_isolation(self):
		with set_user(self.alice):
			result = call_tool("call_method", method="wallet.mcp.tools.list_accounts")["result"]

		names = [account["name"] for account in result["accounts"]]
		self.assertIn("Gate Alice Savings", names)
		self.assertNotIn("Gate Bob Current", names)

	def test_generic_tools_respect_owner_isolation(self):
		with set_user(self.alice):
			with self.assertRaises(frappe.PermissionError):
				call_tool("get_document", doctype=TXN, name=self.bob_txn)

			count = call_tool("count_documents", doctype=TXN, filters={"owner": self.bob})["result"]

		self.assertEqual(count, 0)
