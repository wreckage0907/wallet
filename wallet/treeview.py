# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Owner-aware tree children, replacing `frappe.desk.treeview.get_children` (audit finding 1).

The framework's `_get_children` builds a raw `frappe.qb` query filtered only on the parent
field, `docstatus` and `disabled`. It runs no permission query condition and no
`has_permission` check, so for `Wallet Category` - the app's only tree - it listed every
user's category names to anyone who opened the tree view or called the method directly.

Pointing the tree view at a different method (`wallet_category_tree.js`) only changes what
the desk calls. `frappe.desk.treeview.get_children` is still whitelisted, and so is
`get_all_nodes`, which calls whatever `tree_method` the client names. That is why this is
registered in `override_whitelisted_methods` as well: both `/api/method/` and
`/api/v2/method/`, and `get_all_nodes`, resolve through that override.

The query goes through `frappe.get_list`, so it carries the same permission query condition
as every list view instead of restating the owner filter by hand - Administrator stays
exempt for the same reason it is exempt everywhere else.
"""

import frappe
from frappe.desk import treeview

from wallet.permissions import OWNED_DOCTYPES


@frappe.whitelist()
def get_children(doctype: str, parent: str = "", include_disabled: str | int | bool = False, **filters):
	if doctype not in OWNED_DOCTYPES:
		return treeview.get_children(doctype, parent, include_disabled, **filters)

	if isinstance(include_disabled, str):
		include_disabled = frappe.sbool(include_disabled)

	meta = frappe.get_meta(doctype)
	parent_field = meta.get("nsm_parent_field") or "parent_" + frappe.scrub(doctype)
	title_field = meta.get("title_field") or "name"

	list_filters = {parent_field: parent or ("is", "not set")}
	if meta.has_field("disabled") and not include_disabled:
		list_filters["disabled"] = 0

	return frappe.get_list(
		doctype,
		fields=["name as value", f"{title_field} as title", "is_group as expandable"],
		filters=list_filters,
		order_by=f"{title_field} asc",
	)
