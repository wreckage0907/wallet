# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Coercing statement cells into dates and amounts.

Bank exports are inconsistent in ways that matter:

* dates arrive as real datetime objects from Excel, or as strings in dd/mm/yyyy,
  dd-mm-yy, "01 Apr 2026" and more
* dd/mm vs mm/dd is genuinely ambiguous per cell. It is resolved per *column* instead,
  by looking for any value in the column whose first component exceeds 12. Deciding
  per cell would happily read 05/03 as May 3rd in a March-dated statement
* amounts carry currency symbols, thousands separators, "Cr"/"Dr" suffixes and
  accounting-style parentheses for negatives
"""

import datetime
import re

from frappe.utils import flt

_AMOUNT_CLEAN = re.compile(r"[^\d.,\-()]")
_NUMERIC_DATE = re.compile(r"^\s*(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})")

_TEXT_DATE_FORMATS = (
	"%d %b %Y",
	"%d-%b-%Y",
	"%d/%b/%Y",
	"%d %B %Y",
	"%d-%B-%Y",
	"%b %d %Y",
	"%b %d, %Y",
	"%Y-%m-%d",
	"%Y/%m/%d",
	"%d %b %y",
	"%d-%b-%y",
)


def parse_amount(value) -> float | None:
	"""Return a signed float, or None when the cell holds no amount at all.

	None and 0.0 mean different things here: a debit/credit pair leaves one of the two
	columns genuinely empty, and treating that as 0.0 would make every row look like
	both a debit and a credit.
	"""
	if value is None:
		return None

	if isinstance(value, int | float) and not isinstance(value, bool):
		return float(value)

	text = str(value).strip()
	if not text or text in ("-", "--", "NA", "N/A", "nil", "Nil"):
		return None

	negative = False

	# "1,234.56 Cr" / "1,234.56 Dr" - the suffix carries the sign.
	suffix = re.search(r"\b(cr|dr)\b\.?\s*$", text, flags=re.IGNORECASE)
	if suffix:
		negative = suffix.group(1).lower() == "dr"
		text = text[: suffix.start()]

	cleaned = _AMOUNT_CLEAN.sub("", text).strip()
	if not cleaned:
		return None

	# Accounting style: (1,234.56) means negative.
	if cleaned.startswith("(") and cleaned.endswith(")"):
		negative = True
		cleaned = cleaned[1:-1]

	cleaned = cleaned.replace("(", "").replace(")", "").replace(",", "")
	if cleaned in ("", "-", "."):
		return None

	try:
		amount = float(cleaned)
	except ValueError:
		return None

	if negative:
		amount = -abs(amount)

	return amount


def parse_date(value, dayfirst: bool = True) -> datetime.date | None:
	"""Return a date, or None when the cell is not a date."""
	if value is None:
		return None

	if isinstance(value, datetime.datetime):
		return value.date()
	if isinstance(value, datetime.date):
		return value

	text = str(value).strip()
	if not text:
		return None

	# Strip a trailing time component: "01/04/2026 13:45:00".
	text = re.split(r"\s+", text)[0] if _NUMERIC_DATE.match(text) else text

	match = _NUMERIC_DATE.match(text)
	if match:
		a, b, c = (int(part) for part in match.groups())

		if a > 31:  # yyyy/mm/dd
			year, month, day = a, b, c
		elif dayfirst:
			day, month, year = a, b, c
		else:
			month, day, year = a, b, c

		if year < 100:
			year += 2000 if year < 70 else 1900

		try:
			return datetime.date(year, month, day)
		except ValueError:
			return None

	for fmt in _TEXT_DATE_FORMATS:
		try:
			return datetime.datetime.strptime(text, fmt).date()
		except ValueError:
			continue

	return None


def detect_dayfirst(values: list) -> bool:
	"""Decide dd/mm vs mm/dd for a whole column.

	Any value whose first component exceeds 12 can only be a day, which settles the
	question for every other value in the column. Indian statements are dd/mm, so that
	is the default when the column is genuinely ambiguous.
	"""
	saw_high_first = saw_high_second = False

	for value in values:
		if isinstance(value, datetime.date):
			continue

		match = _NUMERIC_DATE.match(str(value or "").strip())
		if not match:
			continue

		first, second, _ = (int(part) for part in match.groups())
		if first > 31:  # yyyy-mm-dd, tells us nothing about dayfirst
			continue
		if first > 12:
			saw_high_first = True
		if second > 12:
			saw_high_second = True

	if saw_high_second and not saw_high_first:
		return False

	return True
