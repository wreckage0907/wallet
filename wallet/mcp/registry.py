# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Which tools go on which endpoint.

The read tools are defined once and attached to both endpoints. The write endpoint
deliberately carries them: an agent cannot add a transaction well without first resolving
an account name and checking what is already there, and making someone connect two servers
to do one job is bad ergonomics.

`mcp.tool()` returns a decorator that registers the function and hands it back unchanged,
so registration works imperatively - no need to decorate at definition time, which is what
lets one function serve two instances.
"""

from collections.abc import Callable

from frappe_mcp import ToolAnnotations

from wallet.mcp import tools
from wallet.mcp.guard import guarded

_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

#: Safe on any endpoint.
READ_TOOLS: tuple[tuple[Callable, ToolAnnotations], ...] = (
	(tools.list_accounts, ToolAnnotations(title="List Accounts", **_READ)),
	(tools.list_transactions, ToolAnnotations(title="List Transactions", **_READ)),
	(tools.list_categories, ToolAnnotations(title="List Categories", **_READ)),
	(tools.get_spending_summary, ToolAnnotations(title="Get Spending Summary", **_READ)),
)

#: Mutating. Not destructive - it only ever appends - but not idempotent either.
WRITE_TOOLS: tuple[tuple[Callable, ToolAnnotations], ...] = (
	(
		tools.add_transaction,
		ToolAnnotations(
			title="Add Transaction",
			readOnlyHint=False,
			destructiveHint=False,
			idempotentHint=False,
			openWorldHint=False,
		),
	),
)


def _register(mcp, specs: tuple[tuple[Callable, ToolAnnotations], ...]) -> None:
	for fn, annotations in specs:
		mcp.tool(annotations=annotations)(guarded(fn))


def register_read_tools(mcp) -> None:
	"""Attach the read-only tool set."""
	_register(mcp, READ_TOOLS)


def register_write_tools(mcp) -> None:
	"""Attach the read-only tool set plus the mutating tools."""
	_register(mcp, READ_TOOLS + WRITE_TOOLS)
