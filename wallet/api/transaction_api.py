# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""The manual write path for transactions.

One function records a transaction, and everything that lets a person add one by hand
goes through it: the PWA's Add screen over HTTP, and `wallet.mcp.tools.add_transaction`
as a plain Python call. Duplicated once, the two would drift - and the thing that would
drift first is the duplicate pre-check, which is the only reason a colliding entry
reports "you already recorded this" instead of a MariaDB error code.

The MCP tool keeps what is genuinely its own: the `allow_mcp_writes` gate, and turning
the human names a model speaks into docnames. By the time it calls here it holds ids,
which is also what the PWA holds - its selects are populated from permission-filtered
lists, so the id is already in hand and there is nothing to resolve.

!! Ids arriving over HTTP are attacker-controlled. `frappe.get_doc(...).insert()` checks
that the *caller* may create a Wallet Transaction, and Frappe's link validation checks
only that the linked row exists - neither checks it is *theirs*. So `account` and
`category` are permission-checked explicitly below. Without that, a valid session could
post a transaction onto another holder's account by guessing a hash docname, and read
back that account's balance and currency in the response.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from wallet.api.balance import get_account_balance
from wallet.utils.dedup import find_duplicate

#: Named once so the rollback below cannot drift from the savepoint it unwinds to.
_INSERT_SAVEPOINT = "wallet_create_transaction"


@frappe.whitelist(methods=["POST"])
def create_transaction(
	account: str,
	posting_date: str,
	direction: str,
	amount: float,
	description: str | None = None,
	category: str | None = None,
	counterparty: str | None = None,
	payment_mode: str | None = None,
	reference_number: str | None = None,
	notes: str | None = None,
) -> dict:
	"""Record one transaction and report the balance it leaves behind.

	`account` and `category` are docnames, not display names - both doctypes are
	`autoname: hash`, and every caller here already has the id.

	Returns `{"created": False, "reason": "duplicate", "duplicate_of": {...}}` rather than
	throwing when the entry would collide with an existing row, so the caller can show
	what it collided with. Anything genuinely wrong with the input - a bad direction, a
	non-positive amount, a date before the account opened - throws.
	"""
	direction = normalize_direction(direction)

	if flt(amount) <= 0:
		frappe.throw(_("Amount must be a positive number. Use direction Out for money spent."))

	# See the module docstring: this is the check that keeps one holder's money out of
	# another's account, and `frappe.db.get_value` below would happily read across it.
	if not frappe.has_permission("Wallet Account", "read", doc=account):
		raise frappe.PermissionError

	if category and not frappe.has_permission("Wallet Category", "read", doc=category):
		raise frappe.PermissionError

	# Owning a record is not the same as being able to file against it. Both callers
	# already hide disabled rows - the PWA's selects filter `disabled = 0`, and
	# `wallet.mcp.resolve` refuses to resolve one - so a disabled id arriving here means a
	# stale form or a hand-made request, not a choice anyone made. Letting it through is
	# worse than refusing it: `get_overview` and `get_spending_summary` both exclude
	# disabled accounts, so the money would be real and invisible on every screen.
	account_row = frappe.db.get_value("Wallet Account", account, ["account_name", "disabled"], as_dict=True)
	if account_row.disabled:
		frappe.throw(
			_("{0} is closed. Re-open it to record transactions against it.").format(account_row.account_name)
		)

	if category and frappe.db.get_value("Wallet Category", category, "disabled"):
		frappe.throw(
			_("{0} is no longer in use. Pick another category.").format(
				frappe.db.get_value("Wallet Category", category, "category_name")
			)
		)

	posting_date = posting_date or nowdate()
	signed_amount = flt(amount) if direction == "In" else -flt(amount)

	if duplicate := find_duplicate(
		account=account,
		posting_date=posting_date,
		signed_amount=signed_amount,
		description=description,
		reference_number=reference_number,
	):
		return {"created": False, "reason": "duplicate", "duplicate_of": duplicate}

	def build() -> "frappe.model.document.Document":
		return frappe.get_doc(
			{
				"doctype": "Wallet Transaction",
				"account": account,
				"posting_date": posting_date,
				"direction": direction,
				"amount": flt(amount),
				"description": description,
				"category": category or None,
				"counterparty": counterparty,
				"payment_mode": payment_mode,
				"reference_number": reference_number,
				"notes": notes,
				"source": "Manual",
			}
		)

	# The check above is a read and this is a write, so they are not atomic: a save that
	# raced this one can land the very fingerprint the check just found nothing for. That
	# is a double-tapped Save button on a slow connection, not an exotic scenario, and
	# `dedup_hash` being UNIQUE means the database catches it - as a 1062 the caller cannot
	# act on, which is precisely what this endpoint exists to avoid.
	#
	# The savepoint is what makes recovering possible at all: a failed statement leaves the
	# transaction usable only if we can unwind to a known point before retrying.
	frappe.db.savepoint(_INSERT_SAVEPOINT)
	try:
		doc = build()
		doc.insert()
	except frappe.UniqueValidationError:
		frappe.db.rollback(save_point=_INSERT_SAVEPOINT)

		if reference_number:
			# Tier one hashes the reference and nothing else, so the row that beat us to it
			# is the same payment however the rest of the fields differ. Retrying would only
			# collide again.
			duplicate = find_duplicate(
				account=account,
				posting_date=posting_date,
				signed_amount=signed_amount,
				description=description,
				reference_number=reference_number,
			)
			if duplicate:
				return {"created": False, "reason": "duplicate", "duplicate_of": duplicate}
			raise

		# No reference number, so the collision was on the occurrence ordinal - which means
		# the row that raced us is a *different* transaction that happens to look identical.
		# Two identical cash payments on one day are two real payments, so the entry is
		# still owed an insert; a fresh document re-derives the ordinal against the row that
		# just landed. Once only: a second failure is not a race any more.
		doc = build()
		doc.insert()

	# As of the transaction's own date when that is in the future: get_account_balance
	# defaults to today and filters `posting_date <= as_on`, so a future-dated entry would
	# leave the balance unchanged - and the balance is what makes a misread amount visible,
	# exactly for the entries most likely to be mis-typed.
	as_on = max(str(doc.posting_date), nowdate())
	balance = get_account_balance(account, as_on=as_on)

	return {
		"created": True,
		"transaction": {
			"id": doc.name,
			"account": account,
			# Both ids and display names are returned. The PWA has the names already, but
			# the MCP tool answers a model that cannot carry a hash docname across turns,
			# and echoing the caller's own string back at it confirms nothing.
			"account_name": account_row.account_name,
			"posting_date": str(doc.posting_date),
			"direction": doc.direction,
			"amount": flt(doc.amount),
			"currency": doc.currency,
			"description": doc.description,
			"counterparty": doc.counterparty,
			# Not `category` as passed in: categorization rules fill it in when it was left
			# blank, and the caller has no other way to learn what they chose.
			"category": doc.category,
			"category_name": (
				frappe.db.get_value("Wallet Category", doc.category, "category_name")
				if doc.category
				else None
			),
		},
		# The point of returning this: it is where a misread amount becomes visible.
		"account_balance": flt(balance["balance"]),
		"balance_as_on": as_on,
		"currency": balance["currency"],
	}


def normalize_direction(direction: str) -> str:
	"""Accept any casing, reject anything that is not In or Out."""
	normalized = (direction or "").strip().capitalize()
	if normalized not in ("In", "Out"):
		frappe.throw(_('Direction must be "In" or "Out", not {0}.').format(direction))

	return normalized
