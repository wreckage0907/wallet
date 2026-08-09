# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class WalletCategory(NestedSet):
	nsm_parent_field = "parent_wallet_category"

	def validate(self) -> None:
		self.validate_unique_name()
		self.validate_parent_type()

	def validate_unique_name(self) -> None:
		"""Category names are unique per user, not globally - autoname is `hash` precisely
		so that two users can each have their own "Groceries"."""
		existing = frappe.db.exists(
			"Wallet Category",
			{"category_name": self.category_name, "owner": self.owner, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(_("You already have a category named {0}.").format(frappe.bold(self.category_name)))

	def validate_parent_type(self) -> None:
		if not self.parent_wallet_category:
			return

		parent = frappe.db.get_value(
			"Wallet Category", self.parent_wallet_category, ["is_group", "category_type"], as_dict=True
		)
		if not parent.is_group:
			frappe.throw(_("Parent category must be a group."))
		if parent.category_type != self.category_type:
			frappe.throw(
				_("A {0} category cannot sit under a {1} group.").format(
					self.category_type, parent.category_type
				)
			)

	def on_trash(self) -> None:
		super().on_trash()


def get_descendant_names(category: str) -> list[str]:
	"""Every category at or below `category`, via the nested-set range.

	This is why Wallet Category is a tree: rolling "Food & Dining" up over its children
	is one indexed range query rather than recursive Python.
	"""
	lft, rgt = frappe.db.get_value("Wallet Category", category, ["lft", "rgt"])
	if lft is None:
		return [category]

	return frappe.get_all(
		"Wallet Category",
		filters={"lft": [">=", lft], "rgt": ["<=", rgt], "owner": frappe.session.user},
		pluck="name",
	)
