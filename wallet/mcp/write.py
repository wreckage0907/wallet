# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Read-write MCP endpoint, served at `/api/method/wallet.mcp.write.handle_mcp`.

Carries the read tools as well as `add_transaction`; see wallet/mcp/registry.py for why.

The same caveat as the read endpoint applies, and more sharply: the bearer token is
session-wide, so this endpoint's tool list is not the limit of what its token can do.
"""

import frappe
import frappe_mcp
from werkzeug.wrappers import Response

from wallet.mcp.endpoint import serve
from wallet.mcp.registry import register_write_tools

mcp = frappe_mcp.MCP("wallet-write")


@frappe.whitelist(methods=["GET", "POST"])
def handle_mcp() -> Response:
	"""MCP entry point. See wallet/mcp/endpoint.py for why this is not `@mcp.register()`."""
	return serve(mcp, register_write_tools)
