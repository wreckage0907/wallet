# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Install-time setup: roles and per-user default data.

Why this is not a fixture: `sync_fixtures` re-imports on *every* `bench migrate`, so a
category you deleted would come back, and a category you renamed would be reverted.
Seeding once, idempotently, leaves your edits alone.

Why it is per-user: Wallet Category and Wallet Categorization Rule are owner-isolated
(see wallet/permissions.py), so "the default categories" only exist relative to a user.
Seeding runs inside `frappe.set_user()` because `Document.set_user_and_timestamp` sets
`owner` from `frappe.session.user` and would otherwise overwrite anything we assign.
"""

import contextlib

import frappe

from wallet.setup.default_data import DEFAULT_CATEGORIES, DEFAULT_RULES

WALLET_ROLE = "Wallet User"


def before_install() -> None:
	create_wallet_roles()


def after_install() -> None:
	create_wallet_roles()
	for user in get_wallet_users():
		seed_user_defaults(user)
	frappe.db.commit()


def create_wallet_roles() -> None:
	"""Create the Wallet User role.

	Must exist before doctype sync, since every wallet doctype's permissions reference it.
	Called from `before_install` (fresh installs) and from a `pre_model_sync` patch
	(sites where the app was installed before this role existed).
	"""
	if frappe.db.exists("Role", WALLET_ROLE):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": WALLET_ROLE,
			"desk_access": 1,
			"is_custom": 0,
		}
	).insert(ignore_permissions=True)


def get_wallet_users() -> list[str]:
	"""Enabled human users, excluding the framework's built-in accounts."""
	return frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"user_type": "System User",
			"name": ["not in", ("Administrator", "Guest")],
		},
		pluck="name",
	)


@contextlib.contextmanager
def as_user(user: str):
	"""Run a block as `user` so inserted documents are owned by them."""
	original = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(original)


def seed_user_defaults(user: str) -> dict:
	"""Give `user` the default category tree and categorization rules.

	Idempotent: anything already present (by name) is skipped, so this is safe to call
	repeatedly and safe to call after the user has customised their data.
	"""
	if not frappe.db.exists("User", user):
		return {"categories": 0, "rules": 0}

	with as_user(user):
		categories = seed_categories()
		rules = seed_rules()

	return {"categories": categories, "rules": rules}


def seed_categories() -> int:
	"""Insert missing default categories for the current session user. Returns the count."""
	created = 0

	for category_type, groups in DEFAULT_CATEGORIES.items():
		for group_name, icon, children in groups:
			parent_name, was_created = _ensure_category(
				group_name, category_type, icon=icon, is_group=bool(children), default_key=group_name
			)
			created += int(was_created)

			if not parent_name:
				# The group was renamed away and its replacement is not a group - leave it alone.
				continue

			for child_name in children:
				_, was_created = _ensure_category(
					child_name, category_type, parent=parent_name, default_key=child_name
				)
				created += int(was_created)

	return created


def _ensure_category(
	category_name: str,
	category_type: str,
	parent: str | None = None,
	icon: str | None = None,
	is_group: bool = False,
	default_key: str | None = None,
) -> tuple[str | None, bool]:
	"""Return (docname, was_created) for one category owned by the session user.

	Existence is checked by `default_key` first, so a default the user has *renamed* is
	recognised as still present and is not resurrected under its original name. The
	`category_name` check is the second gate: it stops a restore from colliding with a
	category the user created by hand under the same name.
	"""
	user = frappe.session.user

	if default_key:
		existing = frappe.db.get_value(
			"Wallet Category", {"default_key": default_key, "owner": user}
		)
		if existing:
			return existing, False

	existing = frappe.db.get_value("Wallet Category", {"category_name": category_name, "owner": user})
	if existing:
		return existing, False

	doc = frappe.get_doc(
		{
			"doctype": "Wallet Category",
			"category_name": category_name,
			"category_type": category_type,
			"parent_wallet_category": parent,
			"is_group": int(is_group),
			"icon": icon,
			"is_default": int(bool(default_key)),
			"default_key": default_key,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name, True


def seed_rules() -> int:
	"""Insert missing default categorization rules for the current session user."""
	if not frappe.db.table_exists("Wallet Categorization Rule"):
		# Phase 3 has not been migrated yet on this site.
		return 0

	created = 0
	for rule_name, pattern, category_name, direction, priority in DEFAULT_RULES:
		if frappe.db.exists(
			"Wallet Categorization Rule", {"rule_name": rule_name, "owner": frappe.session.user}
		):
			continue

		category = frappe.db.get_value(
			"Wallet Category", {"category_name": category_name, "owner": frappe.session.user}
		)
		if not category:
			# The user deleted or renamed the target category - skip rather than resurrect it.
			continue

		frappe.get_doc(
			{
				"doctype": "Wallet Categorization Rule",
				"rule_name": rule_name,
				"pattern": pattern,
				"match_field": "description",
				"match_type": "Regex",
				"direction_filter": direction,
				"category": category,
				"priority": priority,
				"is_default": 1,
			}
		).insert(ignore_permissions=True)
		created += 1

	return created


def seed_user_defaults_for_new_user(doc, method: str | None = None) -> None:
	"""`User.after_insert` hook - give every new system user their own defaults."""
	if doc.user_type != "System User" or doc.name in ("Administrator", "Guest"):
		return

	seed_user_defaults(doc.name)
