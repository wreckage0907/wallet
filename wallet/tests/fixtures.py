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
	"""A System User with the Wallet role. Idempotent - returns the email either way.

	`in_import` is set for the insert because Frappe throttles user creation at
	`throttle_user_limit` (60) new users an hour, site-wide, to blunt signup abuse. The
	suites here create a couple of holders each and a full run goes well past that in
	minutes, so without this the tail of the suite fails with a bare "Throttled" that has
	nothing to do with what it was testing. `in_import` is the framework's own escape
	hatch for exactly this - bulk creation that is not a signup - and it is set only
	around the insert.
	"""
	if not frappe.db.exists("User", email):
		previous = frappe.flags.in_import
		frappe.flags.in_import = True
		try:
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
					"roles": [{"role": role} for role in roles],
				}
			).insert(ignore_permissions=True)
		finally:
			frappe.flags.in_import = previous

	return email


def delete_user(email: str) -> None:
	"""Remove a user and everything they own, for a suite that needs to watch a *new* one.

	`frappe.delete_doc` rather than `frappe.db.delete`, because a User row has children -
	`Has Role` among them - and dropping the parent alone leaves those behind. Recreating
	the same email then fails with "already has the role X", from whichever other app on
	the site adds a role of its own on user creation.
	"""
	purge(email)
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True, delete_permanently=True)

	# Belt and braces for children orphaned by an earlier run that removed the parent row
	# without them: the User is gone, so the delete above is skipped, but the stale rows
	# still collide with the next insert of the same email.
	frappe.db.delete("Has Role", {"parenttype": "User", "parent": email})


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


def make_bank(bank_name: str = "Test Bank") -> str:
	"""Shared reference data, not owner-isolated - so this is idempotent across suites."""
	existing = frappe.db.get_value("Wallet Bank", {"bank_name": bank_name})
	if existing:
		return existing

	return (
		frappe.get_doc({"doctype": "Wallet Bank", "bank_name": bank_name})
		.insert(ignore_permissions=True)
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


#: A statement shaped like an HDFC export: a branch-detail block, the header, transaction
#: rows, then a summary footer. Header detection has to find the middle band without being
#: fooled by either end, so the junk at both ends is the point.
#:
#: Statements are built in memory rather than checked in. `.gitignore` blocks `*.xlsx` and
#: `*.csv` at the repo root for a reason - a real statement is the natural fixture and the
#: easiest thing in the world to commit by accident.
STATEMENT_HEADER = [
	"Date",
	"Narration",
	"Chq./Ref.No.",
	"Value Dt",
	"Withdrawal Amt.",
	"Deposit Amt.",
	"Closing Balance",
]

STATEMENT_ROWS = [
	# date, narration, ref, value date, withdrawal, deposit, balance
	["02/04/2026", "UPI-SWIGGY-ORDER-9911", "REF001", "02/04/2026", "250.00", "", "99750.00"],
	["03/04/2026", "SALARY CREDIT ACME LTD", "REF002", "03/04/2026", "", "85000.00", "184750.00"],
	# A merchant whose name contains "total". It must be imported, not read as a footer.
	["04/04/2026", "TOTALENERGIES FUEL PUMP", "REF003", "04/04/2026", "2500.00", "", "182250.00"],
	# Two genuinely distinct payments, identical but for the balance they leave behind.
	["05/04/2026", "UPI-CHAI-STALL", "", "05/04/2026", "50.00", "", "182200.00"],
	["05/04/2026", "UPI-CHAI-STALL", "", "05/04/2026", "50.00", "", "182150.00"],
	["06/04/2026", "NACH-EMI-HOMELOAN", "REF004", "06/04/2026", "32000.00", "", "150150.00"],
]

STATEMENT_CLOSING_BALANCE = 150150.0


def statement_grid(rows: list[list] | None = None, header: list | None = None) -> list[list]:
	"""The full grid, junk block and footer included."""
	return [
		["HDFC BANK LTD"],
		["Account Holder", "JANE DOE"],
		["Address", "12 MG Road, Bengaluru"],
		["Statement Period", "01/04/2026 to 30/04/2026"],
		[],
		list(header if header is not None else STATEMENT_HEADER),
		*[list(row) for row in (STATEMENT_ROWS if rows is None else rows)],
		["", "Closing Balance", "", "", "", "", f"{STATEMENT_CLOSING_BALANCE:.2f}"],
		["*** This is a computer generated statement ***"],
	]


def xlsx_bytes(grid: list[list], sheet_name: str = "Statement") -> bytes:
	"""Write a grid to an in-memory xlsx workbook."""
	import io

	import openpyxl

	workbook = openpyxl.Workbook()
	sheet = workbook.active
	sheet.title = sheet_name
	for row in grid:
		sheet.append(row)

	buffer = io.BytesIO()
	workbook.save(buffer)
	return buffer.getvalue()


def csv_bytes(grid: list[list], delimiter: str = ",") -> bytes:
	import csv
	import io

	buffer = io.StringIO()
	writer = csv.writer(buffer, delimiter=delimiter)
	for row in grid:
		writer.writerow(row)

	return buffer.getvalue().encode("utf-8")


def make_import(account: str, content: bytes, file_name: str = "statement.xlsx", **extra) -> str:
	"""A Wallet Statement Import with the statement really attached to it.

	Attached rather than merely referenced: `get_file_content` treats "is this file
	attached to this very import" as the thing that authorises reading it, so a fixture
	that only sets the field would exercise the fallback path instead of the normal one.
	"""
	doc = frappe.get_doc({"doctype": "Wallet Statement Import", "account": account, **extra}).insert()

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"is_private": 1,
			"content": content,
			"decode": False,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "statement_file",
		}
	).insert()

	doc.statement_file = file_doc.file_url
	doc.save()
	return doc.name
