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

For banks that provide neither a reference number nor a running balance we fall back to
an occurrence ordinal. Two things make that ordinal usable:

* the caller passes it explicitly, so an importer can count occurrences *within the file
  it is staging*. Deriving it purely from a database count would give two identical rows
  in the same statement the same ordinal, the same hash, and silently drop the second.
* Wallet Transaction stamps `dedup_hash` once, on insert, and never recomputes it. If the
  hash were recomputed on every save, editing the first of two identical rows would
  re-derive an ordinal that now collides with the second.

It remains the weakest tier: delete one of a duplicate pair and re-import, and the
ordinal no longer lines up. There is nothing better available when the statement carries
neither a reference number nor a running balance.
"""

import hashlib
import re

import frappe
from frappe.utils import flt, getdate, nowdate

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


def content_key(account: str, posting_date, signed_amount: float, description: str | None) -> tuple:
	"""The part of the fingerprint that is pure content, before any discriminator."""
	return (
		account,
		getdate(posting_date).strftime("%Y-%m-%d"),
		f"{flt(signed_amount):.2f}",
		normalize(description),
	)


def build_dedup_hash(
	account: str,
	posting_date,
	signed_amount: float,
	description: str | None = None,
	reference_number: str | None = None,
	balance_after: float | None = None,
	exclude: str | None = None,
	occurrence: int | None = None,
) -> str:
	"""Fingerprint one transaction. See the module docstring for the tiering rationale.

	`occurrence` lets a batch importer supply its own ordinal so that repeated identical
	rows inside one statement stay distinct. When omitted it is derived from the database,
	which is correct only for a single transaction added on its own.
	"""
	if reference_number and normalize(reference_number):
		return _digest(account, "ref", normalize(reference_number))

	key = content_key(account, posting_date, signed_amount, description)

	if balance_after not in (None, ""):
		discriminator = f"bal:{flt(balance_after):.2f}"
	else:
		if occurrence is None:
			occurrence = occurrence_index(*key, exclude=exclude)
		discriminator = f"occ:{occurrence}"

	return _digest(*key, discriminator)


def occurrence_index(
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


def find_duplicate(
	account: str,
	posting_date,
	signed_amount: float,
	description: str | None = None,
	reference_number: str | None = None,
) -> dict | None:
	"""The transaction a new entry would collide with, if any.

	`dedup_hash` is a UNIQUE column, so without this check an insert that fingerprints
	identically raises a raw MariaDB duplicate-key error - which reaches the caller as
	`(1062, ...)` and tells it nothing it can act on. Every manual write path
	(`wallet.api.transaction_api`, and the MCP tool through it) checks here first.

	This only catches what the fingerprint actually treats as the same row. With a
	`reference_number` it is exact. Without one, `build_dedup_hash` falls back to the
	occurrence ordinal above, which deliberately keeps two identical same-day payments
	distinct - so repeat cash entries are allowed through, correctly.

	Goes through `frappe.get_list`, so a fingerprint that collides with *another user's*
	row is not reported: the collision is impossible in the first place, because `account`
	is part of every hash and accounts are owner-scoped.
	"""
	dedup_hash = build_dedup_hash(
		account=account,
		posting_date=posting_date or nowdate(),
		signed_amount=signed_amount,
		description=description,
		reference_number=reference_number,
	)

	existing = frappe.get_list(
		"Wallet Transaction",
		filters={"dedup_hash": dedup_hash},
		fields=["name", "posting_date", "amount", "description"],
		limit_page_length=1,
	)
	if not existing:
		return None

	row = existing[0]
	return {
		"id": row["name"],
		"posting_date": str(row["posting_date"]),
		"amount": flt(row["amount"]),
		"description": row.get("description"),
	}
