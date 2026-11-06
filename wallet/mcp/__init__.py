# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Wallet over MCP, served by Frappe's built-in MCP server at `/api/v2/mcp`.

Wallet no longer runs an MCP endpoint of its own. Frappe (v16.53+) ships one in core: it
authenticates with the site's OAuth stack, and its generic tools go through the same
permission hooks as REST API v2, so owner isolation applies unchanged. This package holds
what Wallet adds on top:

* `tools` - whitelisted, agent-shaped methods an agent reaches with `call_method`.
* `resolve` - human names in, docnames out, for those methods.
* `gate` - the MCP write gate (site switch plus per-user opt-in), on every Wallet document.

`handle_mcp` below is the old endpoint, kept only to tell stale clients where it went.
"""

import json

import frappe
from werkzeug.wrappers import Response

#: Frappe's built-in MCP server, which replaced Wallet's own endpoint.
NEW_ENDPOINT = "/api/v2/mcp"


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle_mcp() -> Response:
	"""Retired. Wallet's MCP endpoint moved to Frappe's built-in server at /api/v2/mcp.

	Kept so that a client still configured with the old URL gets a JSON-RPC error that says
	where to go, instead of a "method not found" traceback. Guest-callable on purpose: an
	unauthenticated client would otherwise start an OAuth flow against a dead URL before
	ever seeing this. It reads nothing and writes nothing.
	"""
	url = frappe.utils.get_url(NEW_ENDPOINT)
	body = {
		"jsonrpc": "2.0",
		"id": None,
		"error": {
			"code": -32600,
			"message": f"This MCP endpoint has moved. Point your MCP client at {url}",
			"data": {"endpoint": url},
		},
	}
	return Response(json.dumps(body), status=410, mimetype="application/json")
