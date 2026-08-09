# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Owner-based data isolation for Wallet.

Every personal record in this app is scoped to the user who created it. There is no
`user` Link field - the framework's `owner` column already carries that, and a second
copy would just be one more thing to keep in sync.

Isolation is enforced in three places, deliberately:

1. `if_owner = 1` on the Wallet User role in each doctype's permissions
   -> covers `frappe.get_doc` / form view.
2. `permission_query_conditions` (this module)
   -> covers list view, report view, and `frappe.get_list`.
3. `has_permission` (this module)
   -> covers direct document access checks.

Only `Administrator` is exempt, deliberately. The usual Frappe habit of exempting
`System Manager` is wrong for a finance app: a System Manager is an ordinary role that
the account holder themselves almost always has, and exempting it would mean your own
list views quietly mix in other people's transactions. Administrator stays exempt purely
as the break-glass account for recovery and debugging.

!! IMPORTANT !!
`frappe.get_all` and `frappe.qb` BYPASS permission query conditions entirely. Any
aggregate in `wallet/api/` must either use `frappe.get_list` (permission-aware) or
carry an explicit `owner = frappe.session.user` filter. This is the single most likely
security bug in this app - grep for `get_all` in code review.
"""

import frappe

#: Doctypes holding personal financial data. `Wallet Bank` and `Wallet Statement Format`
#: are intentionally absent: they are shared reference data with no personal content.
OWNED_DOCTYPES = (
	"Wallet Account",
	"Wallet Transaction",
	"Wallet Category",
	"Wallet Categorization Rule",
	"Wallet Statement Import",
	"Wallet Budget",
)


def get_permission_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	"""Restrict list/report queries to the session user's own records.

	Signature is dictated by the framework: `frappe.model.db_query` calls this as
	`frappe.call(fn, self.user, doctype=self.doctype)`, so the second parameter must be
	named `doctype` and be keyword-defaulted.
	"""
	user = user or frappe.session.user

	if not doctype:
		return ""

	if user == "Administrator":
		return ""

	return f"`tab{doctype}`.`owner` = {frappe.db.escape(user)}"


def has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	"""Allow a user to touch only their own records."""
	user = user or frappe.session.user

	if user == "Administrator":
		return True

	return doc.owner == user
