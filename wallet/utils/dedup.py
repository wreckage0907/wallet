# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Content-derived transaction fingerprints.

Bank statements overlap month to month, so re-import protection cannot be "have I seen
this file before" - the same rows arrive inside different files. The fingerprint is
derived from the transaction's own content instead, and lives on Wallet Transaction
rather than on the import, so it also blocks a manual entry that duplicates an imported
row and survives deletion of the import document.

Two tiers:

1. When the bank supplies a reference number (UTR, cheque no, transaction id), that is
   already a unique key per account - use it directly.
2. Otherwise, hash date + signed amount + normalised description, plus a discriminator.

The discriminator is the interesting part. Two genuinely distinct 50 rupee payments to
the same merchant on the same day would otherwise collide. Nearly every Indian bank
statement carries a running balance column, and the running balance differs between
those two rows - so it separates them for free, with no counting and no dependence on
row order, and stays stable across re-imports and deletions.

KNOWN LIMITATION: for banks that provide neither a reference number nor a running
balance we fall back to counting existing identical rows (`occurrence_index`). That
index is not stable under deletion - if you delete one of a duplicate pair and re-import,
the survivor's index no longer matches and the row is treated as new. This is the least
bad option available without extra information from the statement.
"""

import hashlib
import re

import frappe
from frappe.utils import flt, getdate

_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize(value: str | None) -> str:
	"""Casefold, strip punctuation, collapse whitespace.

	Banks reformat their own narrations between exports (extra spaces, a stray slash),
	and an unnormalised hash would treat those as new transactions.
	"""
	if not value:
		return ""

	text = _PUNCTUATION.sub(" ", str(value))
	return _WHITESPACE.sub(" ", text).strip().casefold()


def _digest(*parts: str) -> str:
	return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_dedup_hash(
	account: str,
	posting_date,
	signed_amount: float,
	description: str | None = None,
	reference_number: str | None = None,
	balance_after: float | None = None,
	exclude: str | None = None,
) -> str:
	"""Fingerprint one transaction. See the module docstring for the tiering rationale."""
	if reference_number and normalize(reference_number):
		return _digest(account, "ref", normalize(reference_number))

	date_key = getdate(posting_date).strftime("%Y-%m-%d")
	amount_key = f"{flt(signed_amount):.2f}"
	description_key = normalize(description)

	if balance_after not in (None, ""):
		discriminator = f"bal:{flt(balance_after):.2f}"
	else:
		discriminator = f"occ:{_occurrence_index(account, date_key, amount_key, description_key, exclude)}"

	return _digest(account, date_key, amount_key, description_key, discriminator)


def _occurrence_index(
	account: str,
	date_key: str,
	amount_key: str,
	description_key: str,
	exclude: str | None = None,
) -> int:
	"""How many transactions already share the first four components.

	Only reached for statements with no reference number and no running balance.
	"""
	candidates = frappe.get_all(
		"Wallet Transaction",
		filters={
			"account": account,
			"posting_date": date_key,
			"signed_amount": flt(amount_key),
			"name": ["!=", exclude or ""],
		},
		fields=["name", "description"],
	)

	return sum(1 for row in candidates if normalize(row.description) == description_key)
