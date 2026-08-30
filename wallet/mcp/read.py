# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Read-only MCP endpoint, served at `/api/method/wallet.mcp.read.handle_mcp`.

!! This is a blast-radius boundary, not a sandbox. A Frappe OAuth bearer token is
session-wide: `frappe.auth.validate_oauth` derives a token's required scopes from the
token itself, so scope checking is tautological and a token issued here can still reach
any whitelisted method on the site as that user. Do not describe this endpoint as safe to
hand to a client you do not trust.
"""

import frappe
import frappe_mcp
from werkzeug.wrappers import Response

from wallet.mcp.endpoint import serve
from wallet.mcp.registry import register_read_tools

mcp = frappe_mcp.MCP("wallet-read")


@frappe.whitelist(methods=["GET", "POST"])
def handle_mcp() -> Response:
	"""MCP entry point. See wallet/mcp/endpoint.py for why this is not `@mcp.register()`."""
	return serve(mcp, register_read_tools)
