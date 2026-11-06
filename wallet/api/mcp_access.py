# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""The PWA's view of the MCP write gate, and the user's own switch in it.

See wallet/mcp/gate.py for how the two switches combine.
"""

import frappe

from wallet.mcp import gate
from wallet.settings import get_setting
from wallet.setup.custom_fields import MCP_OPT_IN_FIELD


@frappe.whitelist(methods=["GET"])
def get_mcp_access() -> dict:
	"""Whether an AI agent connected as the session user may change their Wallet data.

	`writable` is what the gate decides; `site` and `user` say which switch is off.
	"""
	site = bool(get_setting("allow_mcp_writes"))
	user = gate.user_opted_in()
	return {"site": site, "user": user, "writable": site and user}


@frappe.whitelist(methods=["POST"])
def set_mcp_writes(enabled: bool) -> dict:
	"""Opt the session user in to, or out of, MCP writes. Refused over MCP."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(frappe._("Log in first."), frappe.PermissionError)

	gate.assert_can_change_opt_in(user)

	# db.set_value rather than a User save: the only field touched is the user's own, the
	# checks above are the ones the User hook would apply, and a full User save runs
	# validation (passwords, roles, sessions) that has nothing to do with this.
	frappe.db.set_value("User", user, MCP_OPT_IN_FIELD, 1 if enabled else 0)
	return get_mcp_access()
