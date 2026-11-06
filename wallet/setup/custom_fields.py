# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Fields Wallet adds to core doctypes.

The per-user MCP write opt-in lives on `User`, not in a Frappe user default:
`frappe.client.set_default` is whitelisted, so an agent could opt itself in with one
`call_method`. A field changes through a document save, where `wallet.mcp.gate` refuses it
over MCP and refuses it from anyone but the user.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

#: Read by `wallet.mcp.gate`; the PWA's Settings screen flips it via `wallet.api.mcp_access`.
MCP_OPT_IN_FIELD = "wallet_allow_mcp_writes"

CUSTOM_FIELDS = {
	"User": [
		{
			"fieldname": "wallet_section",
			"fieldtype": "Section Break",
			"label": "Wallet",
			"insert_after": "api_secret",
			"module": "Wallet",
		},
		{
			"fieldname": MCP_OPT_IN_FIELD,
			"fieldtype": "Check",
			"label": "Allow AI Agents to Change My Wallet Data",
			"description": (
				"Lets an AI agent you connect over MCP record transactions and change your "
				"Wallet records. Takes effect only while Allow MCP Writes is also on in "
				"Wallet Settings. Only you can change this, and never over MCP."
			),
			"default": "0",
			"insert_after": "wallet_section",
			"module": "Wallet",
		},
	],
}


def create_wallet_custom_fields() -> None:
	"""Idempotent: `create_custom_fields` updates a field that already exists."""
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
