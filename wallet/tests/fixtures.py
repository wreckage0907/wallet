# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Fixture builders shared by the Python suites.

The one module under `wallet/tests/` that mirrors no source file - see
`specs/testing.md`. It exists because every suite needs the same four things (a user, an
account, a category, a transaction) and a copy per file drifts.

Everything here inserts as `frappe.session.user`, so callers wrap them in
`frappe.tests.set_user` to decide who owns what. That is the whole point: owner isolation
is the invariant this app is built on, and a fixture that quietly lands on the wrong owner
makes an isolation test pass for the wrong reason.
"""

import frappe

#: Cleared by `purge`, children before parents. Wallet Statement Import is absent
#: deliberately: it owns Wallet Transaction rows through a Link, so it has to go before
#: them, and no suite here creates one.
OWNED_DOCTYPES = (
	"Wallet Transaction",
	"Wallet Categorization Rule",
	"Wallet Account",
	"Wallet Category",
)


def purge(*users: str) -> None:
	"""Remove every wallet record these users own, children first.

	`frappe.db.delete` skips document hooks, which is what makes the ordering above
	sufficient - nothing runs that would re-create a row we just dropped.

	Wallet Categorization Rule has to go before Wallet Category, and has to be in the list
	at all: `User.after_insert` seeds every new user a set of rules whose `category` is a
	reqd Link into the categories seeded alongside them. Drop the categories alone and
	every rule dangles, so the next fixture whose description matches one dies with
	LinkValidationError.
	"""
	for doctype in OWNED_DOCTYPES:
		for user in users:
			frappe.db.delete(doctype, {"owner": user})


def make_user(email: str, roles: tuple[str, ...] = ("Wallet User",)) -> str:
	"""A System User with the Wallet role. Idempotent - returns the email either way."""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)

	return email


def make_account(
	account_name: str,
	account_type: str = "Savings",
	opening_balance: float = 0,
	opening_date: str = "2020-01-01",
	currency: str = "INR",
	masked_account_number: str | None = None,
	include_in_net_worth: int = 1,
) -> str:
	"""An account owned by the session user. Returns its docname, not its title -
	`autoname` is `hash`, and every API here takes the docname."""
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Account",
				"account_name": account_name,
				"account_type": account_type,
				"currency": currency,
				"masked_account_number": masked_account_number,
				"opening_balance": opening_balance,
				"opening_date": opening_date,
				"include_in_net_worth": include_in_net_worth,
			}
		)
		.insert()
		.name
	)


def make_category(
	category_name: str,
	category_type: str = "Expense",
	is_group: int = 0,
	parent: str | None = None,
) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Category",
				"category_name": category_name,
				"category_type": category_type,
				"is_group": is_group,
				"parent_wallet_category": parent,
			}
		)
		.insert()
		.name
	)


def make_rule(
	rule_name: str,
	pattern: str,
	category: str | None = None,
	match_type: str = "Contains",
	match_field: str = "description",
	direction_filter: str = "Any",
	priority: int = 10,
	**extra,
) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Categorization Rule",
				"rule_name": rule_name,
				"pattern": pattern,
				"category": category,
				"match_type": match_type,
				"match_field": match_field,
				"direction_filter": direction_filter,
				"priority": priority,
				"enabled": 1,
				**extra,
			}
		)
		.insert()
		.name
	)


def make_transaction(
	account: str,
	posting_date: str,
	direction: str,
	amount: float,
	description: str | None = None,
	**extra,
) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Transaction",
				"account": account,
				"posting_date": posting_date,
				"direction": direction,
				"amount": amount,
				"description": description,
				**extra,
			}
		)
		.insert()
		.name
	)


def commit() -> None:
	"""Commit the fixtures a suite built in `setUpClass`, and the teardown that clears them.

	`IntegrationTestCase` rolls back after every test, so fixtures built in `setUpClass`
	and left uncommitted would survive only the first one. Committing them is the whole
	reason class-level fixtures work at all, and it is why `purge` runs at both ends: the
	rows are real, and a crashed run leaves them behind for the next.

	Wrapped in a function rather than called inline so the exemption below is stated once,
	with its reason, instead of thirty times across the suites.
	"""
	# Deliberate, and outside a request: see the docstring. The semgrep rule is aimed at
	# request handlers, where Frappe manages the transaction and a manual commit defeats it.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()
