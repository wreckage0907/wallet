# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import frappe


def execute() -> None:
	"""Composite index behind every balance aggregate.

	`balance()` filters by account and posting_date and sums signed_amount; without this
	the dashboard degrades linearly with transaction count.
	"""
	frappe.db.add_index("Wallet Transaction", ["account", "posting_date"])
