# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Fixture builders shared by the server test suites.

These live here rather than in whichever test module happened to need them first: two
suites building an account two slightly different ways is how a passing test starts
meaning something other than what it says. Not to be confused with
`wallet/tests/e2e_seed.py`, which seeds the *Playwright* fixtures over HTTP - these are
for `IntegrationTestCase`, and are torn down again in the same run.
"""

import frappe


def purge(*users: str) -> None:
	"""Remove every fixture these users own, children first.

	Run at both ends: setUpClass so a crashed run does not poison the next one,
	tearDownClass so the dev site is left as it was found. `frappe.db.delete` skips
	document hooks, which is what makes the ordering here sufficient.
	"""
	# Wallet Categorization Rule first, and it must be here at all: User.after_insert seeds
	# each user a set of rules whose `category` is a reqd Link into the categories seeded
	# alongside them. Dropping the categories without the rules leaves every rule dangling,
	# and the next fixture whose description matches one dies with LinkValidationError.
	for doctype in (
		"Wallet Transaction",
		"Wallet Categorization Rule",
		"Wallet Account",
		"Wallet Category",
	):
		for user in users:
			frappe.db.delete(doctype, {"owner": user})


def make_user(email: str) -> str:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": "Wallet User"}],
			}
		)
		user.insert(ignore_permissions=True)

	return email


def make_account(account_name: str, masked_account_number: str | None = None) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Account",
				"account_name": account_name,
				"account_type": "Savings",
				"currency": "INR",
				"masked_account_number": masked_account_number,
				"opening_balance": 0,
				"opening_date": "2020-01-01",
			}
		)
		.insert()
		.name
	)


def make_category(category_name: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Category",
				"category_name": category_name,
				"category_type": "Expense",
			}
		)
		.insert()
		.name
	)


def make_transaction(account: str, posting_date: str, direction: str, amount: float, description: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Transaction",
				"account": account,
				"posting_date": posting_date,
				"direction": direction,
				"amount": amount,
				"description": description,
			}
		)
		.insert()
		.name
	)
