# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""The tool bodies exposed over MCP.

Plain functions, registered onto an `MCP` instance by `wallet.mcp.registry`. Kept
undecorated here so this module stays importable - and unit-testable - without
`frappe_mcp` installed.

Two rules govern everything in this file:

* **Docstrings are the API contract.** `frappe-mcp` derives the tool description and the
  per-argument JSON Schema descriptions from the Google-style docstring, so this is the
  only thing the model reads before calling. The sign convention especially has to be
  spelled out, or a model will pass a negative amount and trip `validate_amount`.
* **Never `frappe.get_all`.** It bypasses `permission_query_conditions` (see
  wallet/permissions.py), which is the whole basis of this app's data isolation. Every
  query below goes through `frappe.get_list`.

Every tool returns a dict at the top level: `frappe_mcp` only populates
`structuredContent` when the return value is a dict, so bare lists get wrapped.
"""

import frappe
from frappe import _
from frappe.utils import flt

from wallet.api.balance import get_overview
from wallet.api.transaction_api import create_transaction, normalize_direction
from wallet.mcp import resolve
from wallet.settings import get_setting

#: Cap on `list_transactions`, so a broad query cannot bury the model in rows.
MAX_LIMIT = 200


def list_accounts() -> dict:
	"""List every account with its current balance.

	Credit cards are accounts with `type` "Credit Card" and `is_liability` true; a
	negative balance on one is money owed.

	Every account is listed with its own currency. The `assets`, `liabilities` and
	`net_worth` totals cover the default currency ONLY - when `has_other_currencies` is
	true they are not the whole picture, and saying so is better than implying a total
	that excludes an account the user can see in the same response.
	"""
	overview = get_overview()

	return {
		"accounts": [
			{
				"id": account["name"],
				"name": account["account_name"],
				"type": account["account_type"],
				"bank": account.get("bank"),
				"masked_number": account.get("masked_account_number"),
				"currency": account["currency"],
				"balance": flt(account["balance"]),
				"is_liability": bool(account["is_liability"]),
			}
			for account in overview["accounts"]
		],
		"currency": overview["currency"],
		"assets": overview["assets"],
		"liabilities": overview["liabilities"],
		"net_worth": overview["net_worth"],
		"has_other_currencies": overview["has_other_currencies"],
	}


def list_transactions(
	account: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	category: str | None = None,
	direction: str | None = None,
	search: str | None = None,
	limit: int = 50,
) -> dict:
	"""List transactions, most recent first.

	Args:
	    account: Account name, e.g. "HDFC Savings". Omit for all accounts.
	    from_date: Earliest posting date, YYYY-MM-DD.
	    to_date: Latest posting date, YYYY-MM-DD.
	    category: Category name, e.g. "Groceries". Call list_categories for valid names.
	    direction: "In" for money received, "Out" for money spent. Omit for both.
	    search: Text to match against description and counterparty.
	    limit: Maximum rows to return. Defaults to 50, capped at 200.
	"""
	filters = {}

	if account:
		filters["account"] = resolve.account(account)
	else:
		# Same `disabled: 0` convention as list_accounts and get_spending_summary. Without
		# it this tool reports spend list_accounts cannot account for, labelled with the
		# name of an account the model was never shown and cannot ask a follow-up about.
		filters["account"] = [
			"in",
			frappe.get_list("Wallet Account", filters={"disabled": 0}, pluck="name", limit_page_length=0),
		]

	if category:
		filters["category"] = resolve.category(category)

	if direction:
		filters["direction"] = normalize_direction(direction)

	capped = min(max(int(limit), 1), MAX_LIMIT)

	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]
	elif from_date:
		filters["posting_date"] = [">=", from_date]
	elif to_date:
		filters["posting_date"] = ["<=", to_date]

	or_filters = (
		{"description": ["like", f"%{search}%"], "counterparty": ["like", f"%{search}%"]} if search else None
	)

	rows = frappe.get_list(
		"Wallet Transaction",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"posting_date",
			"direction",
			"amount",
			"currency",
			"description",
			"counterparty",
			"category",
			"account",
		],
		order_by="posting_date desc, creation desc",
		# One more than asked for, purely to detect truncation. A model that receives
		# exactly `limit` rows and no signal will happily sum them and report the total
		# as fact - the most likely way this tool produces a confident wrong answer.
		limit_page_length=capped + 1,
	)
	has_more = len(rows) > capped
	rows = rows[:capped]

	categories = resolve.category_names()
	accounts = resolve.account_names()

	return {
		"transactions": [
			{
				"id": row["name"],
				"posting_date": str(row["posting_date"]),
				"direction": row["direction"],
				"amount": flt(row["amount"]),
				"currency": row.get("currency"),
				"description": row.get("description"),
				"counterparty": row.get("counterparty"),
				"category": categories.get(row.get("category")),
				"account": accounts.get(row["account"], row["account"]),
			}
			for row in rows
		],
		"count": len(rows),
		# True means these are the most recent matches, not all of them. Narrow the date
		# range, or use get_spending_summary, which aggregates over everything.
		"has_more": has_more,
	}


def list_categories() -> dict:
	"""List the spending and income categories available for filtering and categorizing.

	Category names from this tool are what `list_transactions` and `add_transaction`
	accept for their `category` argument.
	"""
	rows = frappe.get_list(
		"Wallet Category",
		filters={"disabled": 0},
		fields=["name", "category_name", "category_type", "parent_wallet_category"],
		order_by="category_name asc",
		limit_page_length=0,
	)
	names = {row["name"]: row["category_name"] for row in rows}

	return {
		"categories": [
			{
				"id": row["name"],
				"name": row["category_name"],
				"type": row["category_type"],
				"parent": names.get(row.get("parent_wallet_category")),
			}
			for row in rows
		],
		"count": len(rows),
	}


def get_spending_summary(from_date: str, to_date: str, account: str | None = None) -> dict:
	"""Summarise money in, money out and spending per category over a period.

	Transfers between the user's own accounts are excluded, so the totals reflect real
	income and spending rather than money moved around.

	Reports in the default currency only. Accounts held in other currencies are excluded
	and counted in `excluded_accounts`.

	Args:
	    from_date: Start of the period, YYYY-MM-DD.
	    to_date: End of the period, YYYY-MM-DD.
	    account: Account name to restrict to. Omit for all accounts.
	"""
	currency = get_setting("default_currency") or "INR"

	# `disabled: 0` matches list_accounts, which goes through get_overview. Without it the
	# summary reports spend against closed accounts the model was never shown.
	in_currency = frappe.get_list(
		"Wallet Account",
		filters={"currency": currency, "disabled": 0},
		pluck="name",
		limit_page_length=0,
	)
	total_accounts = len(
		frappe.get_list("Wallet Account", filters={"disabled": 0}, pluck="name", limit_page_length=0)
	)

	if account:
		resolved = resolve.account(account)
		if resolved not in in_currency:
			frappe.throw(_("Account {0} is not held in {1}, the default currency.").format(account, currency))
		in_currency = [resolved]

	if not in_currency:
		frappe.throw(_("No accounts held in {0}, the default currency.").format(currency))

	# Aggregated in Python rather than SQL for the same reason as balance.get_cashflow:
	# transfer exclusion depends on the category's type, which is a second table.
	transfer_categories = set(
		frappe.get_list(
			"Wallet Category",
			filters={"category_type": "Transfer"},
			pluck="name",
			limit_page_length=0,
		)
	)

	rows = frappe.get_list(
		"Wallet Transaction",
		filters={
			"posting_date": ["between", [from_date, to_date]],
			"account": ["in", in_currency],
		},
		fields=["direction", "amount", "category", "is_transfer"],
		limit_page_length=0,
	)

	names = resolve.category_names()
	money_in = money_out = 0.0
	by_category: dict[str | None, dict] = {}

	for row in rows:
		if row.get("is_transfer") or row.get("category") in transfer_categories:
			continue

		amount = flt(row["amount"])
		if row["direction"] == "In":
			money_in += amount
		else:
			money_out += amount

		# Keyed by docname, not label: category_name is not unique per owner, and a real
		# category named "Uncategorized" would otherwise merge with the null bucket.
		key = row.get("category")
		label = names.get(key) or _("Uncategorized")
		bucket = by_category.setdefault(key, {"category": label, "in": 0.0, "out": 0.0, "count": 0})
		bucket["in" if row["direction"] == "In" else "out"] += amount
		bucket["count"] += 1

	return {
		"from_date": from_date,
		"to_date": to_date,
		"currency": currency,
		"money_in": money_in,
		"money_out": money_out,
		"net": money_in - money_out,
		# Biggest spend first: it is the answer to the question that is usually being asked.
		"by_category": sorted(by_category.values(), key=lambda b: b["out"], reverse=True),
		"excluded_accounts": total_accounts - len(in_currency) if not account else 0,
	}


def add_transaction(
	account: str,
	posting_date: str,
	direction: str,
	amount: float,
	description: str | None = None,
	category: str | None = None,
	counterparty: str | None = None,
	payment_mode: str | None = None,
	reference_number: str | None = None,
) -> dict:
	"""Record a transaction on an account.

	Args:
	    account: Account name, e.g. "HDFC Savings". Call list_accounts for valid names.
	    posting_date: Date of the transaction, YYYY-MM-DD.
	    direction: "In" for money received, "Out" for money spent.
	    amount: How much, always a positive number. Use direction to record money leaving.
	    description: What the transaction was for.
	    category: Category name. Left empty, categorization rules may fill it in.
	    counterparty: Who was paid, or who paid.
	    payment_mode: One of UPI, Card, NEFT, IMPS, RTGS, ATM, Cheque, Cash, Auto Debit,
	        Interest, Charges, Other.
	    reference_number: Bank reference, UTR or cheque number, if known.
	"""
	# Checked in the tool body rather than at the endpoint, so it holds however this is
	# reached. A URL-level split would not: the bearer token is session-wide.
	if not get_setting("allow_mcp_writes"):
		frappe.throw(
			_(
				"Recording transactions over MCP is turned off. Enable "
				'"Allow MCP Writes" in Wallet Settings to allow it.'
			)
		)

	result = create_transaction(
		account=resolve.account(account),
		posting_date=posting_date,
		direction=direction,
		amount=amount,
		description=description,
		category=resolve.category(category) if category else None,
		counterparty=counterparty,
		payment_mode=payment_mode,
		reference_number=reference_number,
	)
	if not result["created"]:
		return result

	# Ids out, names in: a model cannot carry an `autoname: hash` docname across turns, so
	# every identifier it is shown is one it could say back. The shape is otherwise exactly
	# what create_transaction returned.
	txn = result["transaction"]
	result["transaction"] = {
		**{k: v for k, v in txn.items() if k not in ("account_name", "category_name")},
		"account": txn["account_name"],
		"category": txn["category_name"],
	}

	return result
