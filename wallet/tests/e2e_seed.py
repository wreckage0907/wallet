# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Fixtures for the Playwright suite, seeded over the real HTTP-facing database.

Run before `npx playwright test`::

    bench --site wallet.test execute wallet.tests.e2e_seed.seed

Why a `bench execute` script rather than something the browser sets up: owner isolation
(see wallet/permissions.py) exempts **Administrator only**, so a suite that logs in as
Administrator proves nothing about the invariant the app is built on. The fixtures
therefore belong to a real user, and creating a user with a known password is not
something the PWA can do for itself.

Two users are seeded. The second one exists purely as a canary: its transaction
description and account name must never appear anywhere in the first user's session. If
a query ever loses its owner condition, `api/isolation.spec.ts` is what catches it.

Idempotent - `seed()` purges its own users' wallet data first, so re-running it against
a site that has already been seeded gives the same result as a fresh one.
"""

import os

import frappe
from frappe.utils import add_days, get_first_day, getdate, nowdate

from wallet.install import as_user, seed_user_defaults

USER = os.environ.get("WALLET_E2E_USER", "wallet-e2e@example.com")
PASSWORD = os.environ.get("WALLET_E2E_PASSWORD", "wallet-e2e-password")
OTHER_USER = os.environ.get("WALLET_E2E_OTHER_USER", "wallet-e2e-other@example.com")

# Every fixture string the specs assert on lives here, so a spec and its fixture cannot
# drift apart silently.
SAVINGS = "E2E Savings"
CREDIT_CARD = "E2E Credit Card"
OTHER_ACCOUNT = "E2E Other Holder Account"

SAVINGS_OPENING = 100000.0
SALARY = 85000.0
COFFEE = 250.0
RENT = 32000.0
GROCERIES = 4200.0

# The canary. Deliberately the largest number in the dataset, so a leak would also move
# every headline figure the dashboard renders.
OTHER_SECRET = 999999.0
OTHER_SECRET_LABEL = "E2E Other Holder Secret Spend"

# Doctypes to clear, children before parents.
OWNED_DOCTYPES = (
	"Wallet Transaction",
	"Wallet Categorization Rule",
	"Wallet Account",
	"Wallet Category",
)


def seed() -> dict:
	"""Create both users and their data. Returns a summary for the CI log."""
	user = _make_user(USER)
	other = _make_user(OTHER_USER)

	purge(user, other)

	# Categories come from the app's own installer rather than being hand-rolled here:
	# a spec that asserts on the default tree should fail when the installer breaks.
	seed_user_defaults(user)
	seed_user_defaults(other)

	with as_user(user):
		savings = _account(SAVINGS, "Savings", opening_balance=SAVINGS_OPENING)
		card = _account(CREDIT_CARD, "Credit Card", opening_balance=0)

		# Anchored inside the current month so the dashboard's "In/Out this month" tiles
		# are non-zero on every day of the year. `_early_this_month` keeps the 1st of the
		# month from pushing a date into the previous one.
		_transaction(savings, nowdate(), "In", SALARY, "E2E Salary Credit", "E2E Employer")
		_transaction(savings, nowdate(), "Out", COFFEE, "E2E Coffee Shop", "E2E Coffee Shop")
		_transaction(savings, _early_this_month(), "Out", RENT, "E2E Rent Payment", "E2E Landlord")
		_transaction(card, _early_this_month(), "Out", GROCERIES, "E2E Grocery Run", "E2E Supermarket")

	with as_user(other):
		other_account = _account(OTHER_ACCOUNT, "Savings", opening_balance=OTHER_SECRET)
		_transaction(other_account, nowdate(), "Out", OTHER_SECRET, OTHER_SECRET_LABEL, OTHER_SECRET_LABEL)

	frappe.db.commit()

	summary = {
		"user": user,
		"other_user": other,
		"accounts": [SAVINGS, CREDIT_CARD],
		"net_worth": net_worth(),
	}
	print(f"Seeded wallet e2e fixtures: {summary}")
	return summary


def net_worth() -> float:
	"""The figure the dashboard must render, derived the same way the app derives it.

	Kept here rather than hard-coded in the spec so changing a fixture amount cannot
	leave a stale expectation behind.
	"""
	savings = SAVINGS_OPENING + SALARY - COFFEE - RENT
	card = -GROCERIES
	return savings + card


def purge(*users: str) -> None:
	"""Delete every wallet record owned by `users`.

	`frappe.db.delete` skips document hooks on purpose: there is nothing to cascade here
	and the alternative (`delete_doc` per row) is slow enough to notice in CI. Nested-set
	children go before their parents, and Wallet Category is dropped wholesale so the
	installer can rebuild the tree cleanly.
	"""
	for user in users:
		for doctype in OWNED_DOCTYPES:
			if frappe.db.table_exists(doctype):
				frappe.db.delete(doctype, {"owner": user})

	frappe.db.commit()


def _make_user(email: str) -> str:
	"""Create (or repair) a Wallet User with a known password."""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": "Wallet User"}],
			}
		).insert(ignore_permissions=True)

	user = frappe.get_doc("User", email)
	if not user.enabled:
		user.enabled = 1
	if not any(row.role == "Wallet User" for row in user.roles):
		user.append("roles", {"role": "Wallet User"})
	# `new_password` is the supported way to set one: assigning to the password field
	# directly stores it in plaintext and never reaches the auth table.
	user.new_password = PASSWORD
	user.save(ignore_permissions=True)

	return email


def _early_this_month() -> str:
	"""The 1st of the current month, or today if the 1st has not happened yet today."""
	first = get_first_day(getdate(nowdate()))
	return str(min(getdate(nowdate()), getdate(add_days(first, 1))))


def _account(account_name: str, account_type: str, opening_balance: float) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Account",
				"account_name": account_name,
				"account_type": account_type,
				"currency": "INR",
				"opening_balance": opening_balance,
				"opening_date": "2020-01-01",
			}
		)
		.insert()
		.name
	)


def _transaction(
	account: str,
	posting_date: str,
	direction: str,
	amount: float,
	description: str,
	counterparty: str,
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
				"counterparty": counterparty,
			}
		)
		.insert()
		.name
	)
