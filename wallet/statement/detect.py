# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Finding the header row and mapping columns to fields.

A bank statement is not a clean table: the first rows are branch details, account
holder name, address and a period summary, and the last rows are totals. The real
header sits somewhere in between, and its labels differ by bank.

The approach is to score every row near the top by how many target fields its cells
look like, and take the best. A row only qualifies if it yields a date column plus at
least one amount column, which is what separates a genuine header from an address line
that happens to contain the word "Date".
"""

import hashlib
import re

#: Header label keywords per target field, longest-first within each list so that
#: "value date" is preferred over "date" when both would match.
COLUMN_KEYWORDS: dict[str, tuple[str, ...]] = {
	"value_date": ("value date", "value dt"),
	"posting_date": (
		"transaction date",
		"txn date",
		"tran date",
		"posting date",
		"post date",
		"date of transaction",
		"date",
	),
	"description": (
		"transaction remarks",
		"narration",
		"particulars",
		"description",
		"remarks",
		"transaction details",
		"details",
	),
	"reference_number": (
		"chq./ref.no.",
		"cheque no",
		"chq no",
		"reference no",
		"ref no",
		"ref.no",
		"transaction id",
		"utr",
		"chq",
		"reference",
	),
	"debit": (
		"withdrawal amt",
		"withdrawal amount",
		"withdrawal",
		"debit amount",
		"debit amt",
		"paid out",
		"debit",
		"dr",
	),
	"credit": (
		"deposit amt",
		"deposit amount",
		"deposit",
		"credit amount",
		"credit amt",
		"paid in",
		"credit",
		"cr",
	),
	"amount": ("transaction amount", "amount (inr)", "amount"),
	"dr_cr_indicator": ("dr / cr", "dr/cr", "cr/dr", "type", "indicator"),
	"balance_after": ("closing balance", "running balance", "balance (inr)", "balance"),
}

#: Rows in the leading block that get scored as candidate headers.
HEADER_SCAN_ROWS = 30

#: Text that marks a summary or footer row rather than a transaction.
#:
#: Deliberately specific. A generic "total" matched any narration containing that
#: substring - a fuel payment to "TotalEnergies", for instance - and because footer
#: detection used to run before parsing, those real transactions were silently dropped.
#: Detection is now date-gated (a row that parses as a dated transaction is never treated
#: as a footer), but keeping the markers narrow avoids relying on that alone.
FOOTER_MARKERS = (
	"opening balance",
	"closing balance",
	"statement summary",
	"grand total",
	"legends",
	"computer generated",
	"end of statement",
	"brought forward",
	"carried forward",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(value) -> str:
	"""Collapse a header cell to comparable text."""
	return _NON_ALNUM.sub(" ", str(value or "").strip().casefold()).strip()


def _match_target(cell: str) -> str | None:
	"""Which target field a header cell names, if any."""
	text = _norm(cell)
	if not text:
		return None

	best: tuple[str, int] | None = None
	for target, keywords in COLUMN_KEYWORDS.items():
		for keyword in keywords:
			normalized = _norm(keyword)
			if text == normalized or text.startswith(normalized) or normalized in text:
				# Longer keyword wins: "value date" beats "date".
				if best is None or len(normalized) > best[1]:
					best = (target, len(normalized))

	return best[0] if best else None


def score_row(row: list) -> dict[str, int]:
	"""Map target field -> column index for one candidate header row."""
	mapping: dict[str, int] = {}

	for index, cell in enumerate(row):
		target = _match_target(cell)
		if target and target not in mapping:
			mapping[target] = index

	return mapping


def is_usable(mapping: dict[str, int]) -> bool:
	"""A header needs a date and some notion of amount to be worth anything."""
	has_date = "posting_date" in mapping or "value_date" in mapping
	has_amount = bool({"debit", "credit", "amount"} & mapping.keys())
	return has_date and has_amount


def detect_header(grid: list[list], scan_rows: int = HEADER_SCAN_ROWS) -> tuple[int, dict[str, int]]:
	"""Return (header_row_index, mapping). Raises nothing - returns (-1, {}) on failure."""
	best_index, best_mapping = -1, {}

	for index, row in enumerate(grid[:scan_rows]):
		mapping = score_row(row)
		if not is_usable(mapping):
			continue

		if len(mapping) > len(best_mapping):
			best_index, best_mapping = index, mapping

	return best_index, best_mapping


def detect_amount_convention(mapping: dict[str, int]) -> str:
	"""How this statement expresses direction."""
	if "debit" in mapping and "credit" in mapping:
		return "Separate Debit/Credit Columns"
	if "dr_cr_indicator" in mapping:
		return "Amount + Dr/Cr Indicator"
	return "Single Signed Amount"


def header_signature(row: list) -> str:
	"""Stable fingerprint of a header row.

	This is what makes a repeat import one click: the same bank exporting the same
	report produces the same signature, so a previously confirmed Wallet Statement
	Format can be looked up directly instead of re-running the heuristic.
	"""
	labels = [_norm(cell) for cell in row if _norm(cell)]
	return hashlib.sha256("|".join(labels).encode("utf-8")).hexdigest()


def is_footer_row(row: list) -> bool:
	"""Summary and total rows must not be imported as transactions."""
	text = " ".join(_norm(cell) for cell in row if cell is not None)
	if not text:
		return False

	return any(marker in text for marker in FOOTER_MARKERS)
