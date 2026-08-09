# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Rule-based auto-categorization.

`categorize` is a pure function over plain dicts, not a Document method, deliberately:
the statement importer needs to categorize staged rows *before* any Wallet Transaction
exists, so it can show you the categories in the preview and let you correct them before
anything is committed.

Rules are fetched once and passed in for batch work - a 500-row import must not issue
500 rule queries.
"""

import re

import frappe
from frappe.utils import flt

#: Fields a rule is allowed to write onto a transaction.
_TARGETS = ("category", "counterparty", "payment_mode")


def get_rules(user: str | None = None) -> list[dict]:
	"""Enabled rules for a user, cheapest-to-match first."""
	user = user or frappe.session.user

	return frappe.get_all(
		"Wallet Categorization Rule",
		# Explicit owner filter: get_all bypasses permission_query_conditions.
		filters={"enabled": 1, "owner": user},
		fields=[
			"name",
			"priority",
			"match_field",
			"match_type",
			"pattern",
			"direction_filter",
			"account_filter",
			"amount_min",
			"amount_max",
			"category",
			"set_counterparty",
			"set_payment_mode",
		],
		order_by="priority asc, creation asc",
	)


def _matches(rule: dict, txn: dict) -> bool:
	if rule.get("direction_filter") and rule["direction_filter"] != "Any":
		if txn.get("direction") != rule["direction_filter"]:
			return False

	if rule.get("account_filter") and txn.get("account") != rule["account_filter"]:
		return False

	amount = flt(txn.get("amount"))
	if rule.get("amount_min") and amount < flt(rule["amount_min"]):
		return False
	if rule.get("amount_max") and amount > flt(rule["amount_max"]):
		return False

	haystack = (txn.get(rule.get("match_field") or "description") or "").strip()
	if not haystack:
		return False

	pattern = rule.get("pattern") or ""
	match_type = rule.get("match_type") or "Contains"

	if match_type == "Contains":
		return pattern.casefold() in haystack.casefold()
	if match_type == "Starts With":
		return haystack.casefold().startswith(pattern.casefold())
	if match_type == "Equals":
		return haystack.casefold() == pattern.casefold()
	if match_type == "Regex":
		try:
			return bool(re.search(pattern, haystack, flags=re.IGNORECASE))
		except re.error:
			# A rule saved before validation tightened, or edited directly in the DB.
			# One bad regex must not break categorization for every other rule.
			return False

	return False


def categorize(txn: dict, rules: list[dict] | None = None) -> dict:
	"""Return the fields the first matching rule wants to set.

	Returns the `_TARGETS` fields plus the name of the rule that matched. Pure: it never
	writes. Call `record_match` when a transaction is actually created - see the note
	there about why counting during preview was wrong.
	"""
	if rules is None:
		rules = get_rules(txn.get("owner"))

	for rule in rules:
		if not _matches(rule, txn):
			continue

		return {
			"category": rule.get("category"),
			"counterparty": rule.get("set_counterparty"),
			"payment_mode": rule.get("set_payment_mode"),
			"rule": rule["name"],
		}

	return {**dict.fromkeys(_TARGETS), "rule": None}


def record_match(rule: str | None) -> None:
	"""Count a rule match, atomically.

	Deliberately separate from `categorize`, which runs while merely *previewing* an
	import: counting there inflated the tally every time a user re-parsed or abandoned a
	statement. A read-modify-write would also lose counts when two imports run at once.
	"""
	if not rule:
		return

	frappe.db.sql(
		"""UPDATE `tabWallet Categorization Rule`
		   SET times_matched = COALESCE(times_matched, 0) + 1
		   WHERE name = %s""",
		rule,
	)
