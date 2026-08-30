# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Balance and net-worth aggregates.

The balance of an account is *computed*, never stored:

    balance(account, as_on) = opening_balance
                            + SUM(signed_amount) for that account
                              where posting_date <= as_on

The alternative - a stored counter incremented in `on_update` and decremented in
`on_trash` - drifts. Edits need a before/after diff (and a two-account fixup when the
account field itself changes), bulk SQL and `frappe.db.delete` skip the hooks entirely,
and a worker that dies mid-import leaves a partially applied delta. Every one of those
failures is cumulative and silent. An aggregate has no state to corrupt: it is immune to
edits, deletions and out-of-order imports, because a sum has no ordering.

`Wallet Account.cached_balance` exists only so a list of accounts renders in one query.
It is refreshed by the very function below, so its worst failure mode is staleness.

!! Every query here must stay permission-aware. `frappe.get_all` bypasses
`permission_query_conditions` (see wallet/permissions.py) - use `frappe.get_list`, or
pass an explicit owner filter.
"""

import frappe
from frappe.utils import flt, now, nowdate

from wallet.settings import get_setting


@frappe.whitelist()
def get_account_balance(account: str, as_on: str | None = None) -> dict:
	"""Balance of one account as on a date (default today)."""
	as_on = as_on or nowdate()

	# frappe.db.get_value bypasses the permission hooks, so without this an authenticated
	# caller could read any account's opening balance and currency by guessing its name.
	if not frappe.has_permission("Wallet Account", "read", doc=account):
		raise frappe.PermissionError

	opening = frappe.db.get_value(
		"Wallet Account", account, ["opening_balance", "currency", "is_liability"], as_dict=True
	)
	if not opening:
		frappe.throw(frappe._("Account {0} not found.").format(account))

	rows = frappe.get_list(
		"Wallet Transaction",
		filters={"account": account, "posting_date": ["<=", as_on]},
		fields=[{"SUM": "signed_amount", "as": "total"}],
	)
	movement = flt(rows[0].total) if rows else 0.0

	return {
		"account": account,
		"as_on": as_on,
		"opening_balance": flt(opening.opening_balance),
		"movement": movement,
		"balance": flt(opening.opening_balance) + movement,
		"currency": opening.currency,
		"is_liability": bool(opening.is_liability),
	}


@frappe.whitelist()
def get_overview(as_on: str | None = None) -> dict:
	"""Per-account balances plus assets, liabilities and net worth - in two queries.

	This is the endpoint the PWA dashboard calls, so it deliberately does not loop over
	`get_account_balance`.
	"""
	as_on = as_on or nowdate()
	base_currency = get_setting("default_currency") or "INR"

	accounts = frappe.get_list(
		"Wallet Account",
		filters={"disabled": 0},
		fields=[
			"name",
			"account_name",
			"account_type",
			"bank",
			"masked_account_number",
			"currency",
			"color",
			"is_liability",
			"include_in_net_worth",
			"opening_balance",
		],
		order_by="account_name asc",
		limit_page_length=0,
	)

	movement_by_account = {
		row.account: flt(row.total)
		for row in frappe.get_list(
			"Wallet Transaction",
			filters={"posting_date": ["<=", as_on]},
			fields=["account", {"SUM": "signed_amount", "as": "total"}],
			group_by="account",
			limit_page_length=0,
		)
	}

	# Totals are kept per currency. Adding a rupee balance to a dollar balance produces a
	# number that is wrong in every currency, so the sum is only ever taken within one.
	by_currency: dict[str, dict] = {}

	for account in accounts:
		account["balance"] = flt(account.opening_balance) + movement_by_account.get(account.name, 0.0)

		if not account.include_in_net_worth:
			continue

		bucket = by_currency.setdefault(
			account.currency or base_currency, {"assets": 0.0, "liabilities": 0.0}
		)
		# The sign convention already does the work: a spent-on credit card is negative,
		# so net worth is a plain sum. `is_liability` only flips the label in the UI.
		if account["balance"] < 0:
			bucket["liabilities"] += account["balance"]
		else:
			bucket["assets"] += account["balance"]

	for currency, bucket in by_currency.items():
		bucket["currency"] = currency
		bucket["liabilities"] = abs(bucket["liabilities"])
		bucket["net_worth"] = bucket["assets"] - bucket["liabilities"]

	base = by_currency.get(base_currency, {"assets": 0.0, "liabilities": 0.0, "net_worth": 0.0})

	return {
		"as_on": as_on,
		"accounts": accounts,
		"currency": base_currency,
		"assets": base["assets"],
		"liabilities": base["liabilities"],
		"net_worth": base["net_worth"],
		"by_currency": sorted(by_currency.values(), key=lambda b: b["currency"] != base_currency),
		# The headline figures cover `currency` only; the UI must say so when this is set.
		"has_other_currencies": len(by_currency) > 1,
	}


@frappe.whitelist()
def get_cashflow(from_date: str, to_date: str, account: str | None = None) -> dict:
	"""Money in and money out over a period, excluding transfers between own accounts."""
	filters = {"posting_date": ["between", [from_date, to_date]]}
	if account:
		filters["account"] = account

	transfer_categories = frappe.get_list(
		"Wallet Category", filters={"category_type": "Transfer"}, pluck="name", limit_page_length=0
	)

	rows = frappe.get_list(
		"Wallet Transaction",
		filters=filters,
		fields=["name", "direction", "amount", "category", "is_transfer"],
		limit_page_length=0,
	)

	money_in = money_out = 0.0
	for row in rows:
		if row.is_transfer or (row.category and row.category in transfer_categories):
			continue
		if row.direction == "In":
			money_in += flt(row.amount)
		else:
			money_out += flt(row.amount)

	return {
		"from_date": from_date,
		"to_date": to_date,
		"money_in": money_in,
		"money_out": money_out,
		"net": money_in - money_out,
	}


def refresh_cached_balance(account: str) -> float:
	"""Recompute and store `cached_balance` for one account."""
	if not account:
		return 0.0

	balance = get_account_balance(account)["balance"]
	frappe.db.set_value(
		"Wallet Account",
		account,
		{"cached_balance": balance, "balance_last_updated": now()},
		update_modified=False,
	)
	return balance


@frappe.whitelist(methods=["POST"])
def rebuild_balances() -> dict:
	"""Recompute every cached balance for the session user.

	The explicit repair path for `cached_balance` staleness - exposed as a button on the
	account form and run nightly by the scheduler.
	"""
	accounts = frappe.get_list("Wallet Account", pluck="name", limit_page_length=0)
	for account in accounts:
		refresh_cached_balance(account)

	frappe.db.commit()
	return {"rebuilt": len(accounts)}


def rebuild_all_balances() -> None:
	"""Scheduled daily rebuild across all users. Runs as Administrator, so it must not
	rely on the permission-filtered helpers above."""
	for account in frappe.get_all("Wallet Account", pluck="name"):
		refresh_cached_balance(account)

	frappe.db.commit()
