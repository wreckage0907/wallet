# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Run code the way Frappe's built-in MCP server would."""

from collections.abc import Iterator
from contextlib import contextmanager

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request


@contextmanager
def mcp_request() -> Iterator[None]:
	"""Mark the current request as an MCP one, as `frappe.mcp.transport` does.

	A real `POST /api/v2/mcp` request is installed too: `call_method` downgrades a GET-only
	method by rewriting `frappe.request.method`, so it needs one to rewrite.
	"""
	from frappe.mcp.transport import RequestContext

	original_request = getattr(frappe.local, "request", None)
	original_context = getattr(frappe.local, "mcp_request", None)
	frappe.local.request = Request(EnvironBuilder(method="POST", path="/api/v2/mcp").get_environ())
	frappe.local.mcp_request = RequestContext()
	try:
		yield
	finally:
		frappe.local.mcp_request = original_context
		frappe.local.request = original_request


def call_tool(tool: str, /, **arguments) -> dict:
	"""One `tools/call` through Frappe's built-in tool registry, as an MCP client makes it.

	Returns the structured result. A failing tool raises, exactly as it does inside the
	server before `frappe.app` rolls back and turns the exception into an `isError` result.
	"""
	from frappe.mcp import tools

	with mcp_request():
		return tools.call({"name": tool, "arguments": arguments})["structuredContent"]
