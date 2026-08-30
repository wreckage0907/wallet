# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tool registration.

`mcp.tool()` returns a decorator that registers the function and hands it back unchanged,
so registration works imperatively. The tool bodies in `wallet.mcp.tools` stay undecorated
as a result, which keeps them importable - and unit-testable - without `frappe_mcp`.
"""

from collections.abc import Callable

from frappe_mcp import ToolAnnotations

from wallet.mcp import tools
from wallet.mcp.guard import guarded

_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

#: Annotations are how MCP expresses "this one only looks, that one changes something".
#: Clients use them to gate and confirm, which is the layer this belongs in - the
#: server-side gate on writes is `Wallet Settings.allow_mcp_writes`, checked in the tool.
TOOLS: tuple[tuple[Callable, ToolAnnotations], ...] = (
	(tools.list_accounts, ToolAnnotations(title="List Accounts", **_READ)),
	(tools.list_transactions, ToolAnnotations(title="List Transactions", **_READ)),
	(tools.list_categories, ToolAnnotations(title="List Categories", **_READ)),
	(tools.get_spending_summary, ToolAnnotations(title="Get Spending Summary", **_READ)),
	(
		tools.add_transaction,
		ToolAnnotations(
			title="Add Transaction",
			readOnlyHint=False,
			# It only ever appends, and never twice for the same reference number.
			destructiveHint=False,
			idempotentHint=False,
			openWorldHint=False,
		),
	),
)


def register_tools(mcp) -> None:
	"""Attach every tool, each wrapped in the rollback guard.

	`guarded` must wrap every tool, not just the writing ones: the rule "all tools go
	through the guard" can be checked by looking, where "the write tools go through the
	guard" has to be remembered.
	"""
	for fn, annotations in TOOLS:
		mcp.tool(annotations=annotations)(guarded(fn))
