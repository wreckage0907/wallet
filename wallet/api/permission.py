# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import frappe


def has_app_permission() -> bool:
	"""Gate for the apps screen. Anyone who can keep their own transactions gets Wallet."""
	if frappe.session.user == "Administrator":
		return True

	return bool({"Wallet User", "System Manager"} & set(frappe.get_roles()))
