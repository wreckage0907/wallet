# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""The Wallet MCP endpoint, served at `/api/method/wallet.mcp.handle_mcp`.

One endpoint, not one per access level. Splitting reads and writes across two URLs looks
like a boundary and is not one: a Frappe OAuth bearer token is session-wide, so a token
issued for a "read-only" URL can POST to the write URL just as easily. Read-only is only a
guarantee if it is enforced somewhere the caller cannot route around, so `add_transaction`
checks `Wallet Settings.allow_mcp_writes` in the tool body itself. Which tools an agent
should reach for is expressed the way MCP intends - `readOnlyHint` and `destructiveHint`
annotations, which clients use to gate and confirm.

!! Still not a sandbox. The bearer token remains session-wide, so a client holding one can
reach any whitelisted method on the site as that user. `allow_mcp_writes` closes the
Wallet write path specifically; it does not contain a hostile client.

We deliberately do NOT use `@mcp.register()`, the decorator the library advertises. It
wraps the endpoint in a closure defined inside `frappe_mcp.server.server`, and
`frappe.utils.typing_validations.validate_argument_types` derives the owning app from
`func.__module__.split(".")[0]`. That resolves to `frappe_mcp`, Frappe then tries to import
`frappe_mcp.hooks`, and every request dies with `ModuleNotFoundError`. `mcp.handle()` is
the library's supported entry point for mounting on any Werkzeug app, and returning a
`werkzeug.Response` from a whitelisted method is supported by `frappe.handler.handle`.

The trade-off: `frappe-mcp check` finds handlers by looking for `@mcp.register()`, so it
reports this one as "not properly registered". Cosmetic - a `tools/list` call is the real
verification. Drop the shim if the library starts preserving the wrapped module.

`frappe_mcp` is imported lazily so that `wallet.mcp.tools` and `wallet.mcp.resolve` stay
importable - and testable - on a bench where the library is not installed.
"""

import frappe
from werkzeug.wrappers import Response

_mcp = None


def _get_server():
	"""The MCP instance, built and populated once per process."""
	global _mcp

	if _mcp is None:
		import frappe_mcp

		from wallet.mcp.registry import register_tools

		server = frappe_mcp.MCP("wallet")
		register_tools(server)
		_mcp = server

	return _mcp


@frappe.whitelist(methods=["GET", "POST"])
def handle_mcp() -> Response:
	"""MCP entry point."""
	return _get_server().handle(frappe.request, Response())
