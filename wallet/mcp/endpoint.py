# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Serving an MCP instance from a whitelisted method.

We deliberately do NOT use `@mcp.register()`, the decorator the library advertises.

`register` wraps the endpoint in a closure defined inside `frappe_mcp.server.server`, and
`frappe.utils.typing_validations.validate_argument_types` derives the owning app from
`func.__module__.split(".")[0]`. That resolves to `frappe_mcp`, so Frappe then tries to
import `frappe_mcp.hooks`, which does not exist, and every request dies with
`ModuleNotFoundError: No module named 'frappe_mcp.hooks'`.

`mcp.handle(request, response)` is the library's supported entry point for exactly this -
it is what you would use to mount an MCP server on any other Werkzeug app. Calling it from
a function defined in *our* module keeps `__module__` inside `wallet`, so hook resolution
finds `wallet.hooks` and works. Returning a `werkzeug.Response` from a whitelisted method
is supported by `frappe.handler.handle`.

The trade-off: `frappe-mcp check` discovers handlers by looking for `@mcp.register()`, so
it reports ours as "not properly registered". That is cosmetic - the endpoints work - but
it means the CLI is not a useful verification step for this app. A `tools/list` call is.

Upstream issue to file; drop this shim if `frappe-mcp` starts preserving the wrapped
function's module.
"""

from collections.abc import Callable

import frappe
from werkzeug.wrappers import Response


def serve(mcp, register_tools: Callable) -> Response:
	"""Register this endpoint's tools and hand the request to the MCP server."""
	register_tools(mcp)

	return mcp.handle(frappe.request, Response())
