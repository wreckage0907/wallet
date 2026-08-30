# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Human names in, docnames out.

`Wallet Account` and `Wallet Category` are both `autoname: hash`, so their docnames are
opaque ids like `a1b2c3d4e5`. An LLM cannot be handed one of those and expected to carry
it correctly across turns, so every tool argument that identifies an account or a category
takes the name a person would say.

A failed lookup throws with the list of valid options. That is the whole point: a model
that gets told what it may say next recovers in one turn, where a bare "not found" makes
it guess again.

Lookups go through `frappe.get_list`, so they are permission-filtered - a name that
belongs to another user is not resolvable and does not appear in the options.
"""

import frappe
from frappe import _


def _lookup(doctype: str, label_field: str, value: str) -> str:
	"""Docname for `value`, matched against `label_field` then the docname itself."""
	if not value:
		frappe.throw(_("A {0} name is required.").format(doctype))

	rows = frappe.get_list(
		doctype,
		or_filters={label_field: value, "name": value},
		fields=["name", label_field],
		limit_page_length=0,
	)

	# Case-insensitive fallback. MariaDB collates case-insensitively by default, so this
	# is belt-and-braces for sites configured otherwise.
	if not rows:
		wanted = value.strip().casefold()
		rows = [
			row
			for row in frappe.get_list(doctype, fields=["name", label_field], limit_page_length=0)
			if (row.get(label_field) or "").strip().casefold() == wanted
		]

	if not rows:
		frappe.throw(
			_("No {0} named {1}. Available: {2}").format(
				doctype, value, ", ".join(options(doctype, label_field)) or _("none")
			)
		)

	if len(rows) > 1:
		frappe.throw(
			_("{0} {1} is ambiguous - {2} records share that name. Use the id instead: {3}").format(
				doctype, value, len(rows), ", ".join(row["name"] for row in rows)
			)
		)

	return rows[0]["name"]


def options(doctype: str, label_field: str) -> list[str]:
	"""Every name the session user may refer to, for use in error messages."""
	return sorted(
		row[label_field]
		for row in frappe.get_list(doctype, fields=[label_field], limit_page_length=0)
		if row.get(label_field)
	)


def account(value: str) -> str:
	"""Docname of the account called `value`."""
	return _lookup("Wallet Account", "account_name", value)


def category(value: str) -> str:
	"""Docname of the category called `value`."""
	return _lookup("Wallet Category", "category_name", value)


def category_names() -> dict[str, str]:
	"""Docname -> display name, for labelling transactions on the way out."""
	return {
		row["name"]: row["category_name"]
		for row in frappe.get_list("Wallet Category", fields=["name", "category_name"], limit_page_length=0)
	}


def account_names() -> dict[str, str]:
	"""Docname -> display name."""
	return {
		row["name"]: row["account_name"]
		for row in frappe.get_list("Wallet Account", fields=["name", "account_name"], limit_page_length=0)
	}
