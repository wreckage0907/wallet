# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""The MCP write gate, enforced at the document layer.

A write over MCP needs two switches on:

* `Wallet Settings.allow_mcp_writes` - the site's administrator allows MCP writes at all.
* `User.wallet_allow_mcp_writes` - this user opted in, for themselves. Off by default, so
  one administrator flipping the site switch opens nobody's write path on their behalf.

Frappe's built-in MCP server (`/api/v2/mcp`) hands every agent generic tools -
`create_document`, `update_document`, `delete_document`, `call_method` - so a check inside
one Wallet tool body covers nothing: the agent can create a `Wallet Transaction` without
ever touching it. The gate therefore sits where every write path converges, the
document's own events, wired for every Wallet doctype in `hooks.py`. `Wallet Settings` is
one of them, so an agent can never switch the site gate on, and `guard_opt_in` keeps it
off the user's opt-in.

The few writes that skip document events (`frappe.db.set_value` on a cached balance) call
`check()` explicitly.

"Is this an MCP request" is `frappe.local.mcp_request`, which `frappe.mcp.transport` sets
for the whole of one. It is a framework internal, not an API, so a test pins it: if it is
ever renamed, CI fails instead of the gate silently opening.
"""

import frappe
from frappe import _

from wallet.settings import get_setting
from wallet.setup.custom_fields import MCP_OPT_IN_FIELD


def is_mcp_request() -> bool:
	return getattr(frappe.local, "mcp_request", None) is not None


def user_opted_in(user: str | None = None) -> bool:
	return bool(frappe.db.get_value("User", user or frappe.session.user, MCP_OPT_IN_FIELD))


def check() -> None:
	"""Refuse the current write if it arrives over MCP without both switches on."""
	if not is_mcp_request():
		return

	if not get_setting("allow_mcp_writes"):
		frappe.throw(
			_(
				"Changing Wallet data over MCP is turned off for this site. An administrator "
				'can enable "Allow MCP Writes" in Wallet Settings.'
			),
			frappe.PermissionError,
		)

	if not user_opted_in():
		frappe.throw(
			_(
				"You have not allowed AI agents to change your Wallet data. Turn on "
				'"Let AI agents make changes" in the Wallet app\'s settings to allow it.'
			),
			frappe.PermissionError,
		)


def on_write(doc, method=None) -> None:
	"""`doc_events` handler for every Wallet doctype."""
	check()


def guard_opt_in(doc, method=None) -> None:
	"""`User.validate`: only the user may change their own opt-in, and never over MCP.

	Not an administrator on their behalf - the opt-in exists so that the decision is each
	user's - and not an agent, which would otherwise opt itself in with one
	`update_document`.
	"""
	if doc.is_new():
		if doc.get(MCP_OPT_IN_FIELD):
			frappe.throw(_("A new user cannot start opted in to MCP writes."), frappe.PermissionError)
		return

	if not doc.has_value_changed(MCP_OPT_IN_FIELD):
		return

	assert_can_change_opt_in(doc.name)


def assert_can_change_opt_in(user: str) -> None:
	if is_mcp_request():
		frappe.throw(
			_("Whether AI agents may change your Wallet data cannot be changed over MCP."),
			frappe.PermissionError,
		)

	if user != frappe.session.user:
		frappe.throw(
			_("Only {0} can allow AI agents to change their Wallet data.").format(user),
			frappe.PermissionError,
		)
