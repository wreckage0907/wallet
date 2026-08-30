# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Rollback safety net for MCP tools.

`frappe_mcp` catches every tool exception and returns `isError: true` over HTTP 200.
Frappe's request teardown then sees a successful request and commits, so a `frappe.throw`
partway through a write would leave partial state committed - the exception never reaches
the framework, so nothing else rolls it back.

Applied to read tools too, deliberately. "Every tool goes through the guard" is a rule you
can check by looking; "the write tools go through the guard" is a rule you have to
remember.
"""

import functools
from collections.abc import Callable

import frappe


def guarded(fn: Callable) -> Callable:
	"""Roll back the transaction before the exception is swallowed upstream."""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except Exception:
			frappe.db.rollback()
			raise

	return wrapper
