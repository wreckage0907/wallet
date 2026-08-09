# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Whitelisted setup endpoints for the Wallet PWA.

Note on signatures: hooks.py sets `require_type_annotated_api_methods = True`, so every
parameter of every whitelisted method must carry a type annotation - an unannotated one
raises FrappeTypeError at call time (frappe/utils/typing_validations.py). Optional
parameters must be written `str | None = None`, never a bare `str = None`, because the
values are coerced through pydantic.
"""

import frappe

from wallet.install import seed_user_defaults


@frappe.whitelist()
def ensure_setup() -> dict:
	"""Lazy safety net called on PWA boot.

	Covers users who existed before the app was installed and any case where the
	`User.after_insert` hook did not fire.
	"""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(frappe._("Please log in."), frappe.PermissionError)

	has_categories = frappe.db.exists("Wallet Category", {"owner": user})
	if has_categories:
		return {"seeded": False, "categories": 0, "rules": 0}

	result = seed_user_defaults(user)
	return {"seeded": True, **result}


@frappe.whitelist(methods=["POST"])
def restore_default_categories() -> dict:
	"""Recreate any shipped default category the user deleted.

	Non-destructive: anything still present (matched by name) is left exactly as it is,
	including renames and re-parenting. Only genuinely missing names are recreated.
	"""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(frappe._("Please log in."), frappe.PermissionError)

	result = seed_user_defaults(user)
	return {"restored": result["categories"], "rules_restored": result["rules"]}
