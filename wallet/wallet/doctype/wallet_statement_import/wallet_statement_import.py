# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Statement import: file in, staged rows out, transactions on commit.

Staging lives in a real child table rather than a JSON blob because the whole point of
the preview is that you can *edit* it - fix a category, skip a row - before anything is
committed. Core Data Import re-parses its file on every preview render precisely because
it has nowhere to keep per-row state.

Nothing is written to Wallet Transaction until `commit_rows`, and each row commits inside
its own savepoint, so one bad row can never abort the batch.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from wallet.categorization import categorize, get_rules
from wallet.settings import get_setting
from wallet.statement import detect
from wallet.statement.parse import detect_dayfirst, parse_amount, parse_date
from wallet.api.balance import refresh_cached_balance
from wallet.statement.reader import read_grid
from wallet.utils.dedup import build_dedup_hash, content_key, occurrence_index


class WalletStatementImport(Document):
	# ------------------------------------------------------------------ file access
	def get_file_content(self) -> bytes:
		if not self.statement_file:
			frappe.throw(_("Attach a statement file first."))

		file_doc = frappe.get_doc("File", {"file_url": self.statement_file})

		# `statement_file` is an Attach field, i.e. arbitrary text, so it can be pointed at
		# any file URL on the site including another user's private upload. The only
		# legitimate case is a file attached to this very import.
		attached_here = (
			file_doc.attached_to_doctype == self.doctype and file_doc.attached_to_name == self.name
		)
		if not attached_here:
			file_doc.check_permission("read")
			if file_doc.owner != frappe.session.user and frappe.session.user != "Administrator":
				frappe.throw(_("That file does not belong to you."), frappe.PermissionError)

		return file_doc.get_content(encodings=[])

	# ------------------------------------------------------------------ parsing
	def parse(self, password: str | None = None) -> dict:
		"""Read the file, detect the layout, and stage every transaction row."""
		self.status = "Parsing"
		self.save(ignore_permissions=True)

		password = password or self.get_password("file_password", raise_exception=False)

		try:
			grid, _sheet = read_grid(
				self.get_file_content(),
				file_name=self.statement_file,
				password=password,
				sheet_name=self.get_format_value("sheet_name"),
			)
			result = self._stage_rows(grid)
		except Exception as e:
			self.status = "Failed"
			self.error_log = str(e)
			self.save(ignore_permissions=True)
			raise

		# The password has done its job; keep it no longer than necessary.
		self.file_password = None
		self.status = "Preview Ready"
		self.save(ignore_permissions=True)
		return result

	def get_statement_format(self):
		"""The format governing this import: the one chosen here, else the account's default."""
		name = self.statement_format or frappe.db.get_value(
			"Wallet Account", self.account, "default_statement_format"
		)
		return frappe.get_cached_doc("Wallet Statement Format", name) if name else None

	def get_format_value(self, fieldname: str, default=None):
		fmt = self.get_statement_format()
		value = fmt.get(fieldname) if fmt else None
		return default if value in (None, "") else value

	def _resolve_layout(self, grid: list[list]) -> tuple[int, dict, str]:
		"""Return (header_row, mapping, source) using the cheapest path available.

		Order matters: an explicitly chosen format wins, then a remembered format matched
		by header signature (the one-click repeat import), then the heuristic.
		"""
		fmt = self.get_statement_format()
		if fmt:
			# Adopt it onto the document so the rest of the pipeline and the UI agree on
			# which format is in force, including when it came from the account default.
			self.statement_format = fmt.name
			header_row = fmt.header_row or detect.detect_header(grid)[0]
			mapping = {
				target: spec["index"] for target, spec in fmt.get_mapping().items() if spec["index"] is not None
			}
			if mapping:
				return header_row, mapping, "format"

		header_row, mapping = detect.detect_header(grid)
		if header_row < 0:
			frappe.throw(
				_(
					"Could not find a transaction table in this file. It needs a date column "
					"and at least one amount column."
				)
			)

		signature = detect.header_signature(grid[header_row])
		remembered = frappe.db.get_value(
			"Wallet Statement Format", {"header_signature": signature}, "name"
		)
		if remembered and not self.statement_format:
			self.statement_format = remembered
			fmt = frappe.get_doc("Wallet Statement Format", remembered)
			saved = {
				target: spec["index"] for target, spec in fmt.get_mapping().items() if spec["index"] is not None
			}
			if saved:
				return header_row, saved, "remembered"

		return header_row, mapping, "detected"

	def _stage_rows(self, grid: list[list], mapping_override: dict | None = None) -> dict:
		if mapping_override:
			# The user corrected a mis-detected column; keep the header row we already
			# found and re-stage against their mapping.
			header_row = self.header_row if self.header_row is not None else detect.detect_header(grid)[0]
			mapping, source = mapping_override, "manual"
		else:
			header_row, mapping, source = self._resolve_layout(grid)

		max_rows = get_setting("max_import_rows") or 5000

		# A format may pin where the data starts and how many trailing summary rows to
		# drop; both default to "straight after the header, keep everything".
		data_start = self.get_format_value("data_start_row") or (header_row + 1)
		skip_footer = self.get_format_value("skip_footer_rows") or 0
		body = grid[data_start:]
		if skip_footer:
			body = body[: len(body) - skip_footer]

		if len(body) > max_rows:
			frappe.throw(
				_("This statement has {0} rows, more than the {1} row limit in Wallet Settings.").format(
					len(body), max_rows
				)
			)

		date_column = mapping.get("posting_date", mapping.get("value_date"))
		if date_column is None:
			frappe.throw(_("The column mapping needs a date column."))

		# A saved format states its own date convention; only guess when it does not.
		fmt = self.get_statement_format()
		if fmt and fmt.get("dayfirst") is not None and not mapping_override:
			dayfirst = bool(fmt.dayfirst)
		else:
			dayfirst = detect_dayfirst([row[date_column] for row in body if date_column < len(row)])

		self.header_row = header_row
		# Remembering the header labels means "Save as Format" never has to re-read the
		# file, which it could not do anyway once the password has been cleared.
		if header_row is not None and 0 <= header_row < len(grid):
			self.header_labels = json.dumps(
				[str(cell) if cell is not None else "" for cell in grid[header_row]]
			)
		self.detected_mapping = json.dumps(mapping, indent=1, sort_keys=True)
		self.set("rows", [])

		rules = get_rules(self.owner)
		staged, errors = [], []
		opening_balance = closing_balance = None

		for offset, raw_row in enumerate(body):
			absolute_index = data_start + offset

			parsed = self._parse_row(raw_row, mapping, dayfirst)

			# Summary lines are recognised only *after* failing to parse as a transaction.
			# Checking markers first meant a real dated payment to a merchant like
			# "TotalEnergies" matched the generic marker "total" and was silently dropped.
			if parsed is None:
				opening_balance, closing_balance = self._capture_summary_balance(
					raw_row, mapping, opening_balance, closing_balance
				)
				continue

			if parsed.get("error"):
				errors.append({"row": absolute_index, "message": parsed["error"]})

			parsed["row_index"] = absolute_index
			parsed["raw"] = json.dumps([_jsonable(cell) for cell in raw_row])
			staged.append(parsed)

		self._apply_categories(staged, rules)
		self._apply_dedup(staged)

		for row in staged:
			# `error` is scratch state used while staging, not a child-table field.
			row.pop("error", None)
			self.append("rows", row)

		dates = [row["posting_date"] for row in staged if row.get("posting_date")]
		self.period_from = min(dates) if dates else None
		self.period_to = max(dates) if dates else None
		self.statement_opening_balance = opening_balance
		self.statement_closing_balance = (
			closing_balance
			if closing_balance is not None
			else _last_running_balance(staged)
		)

		self.total_rows = len(staged)
		self.new_rows = sum(1 for row in staged if row["status"] == "New")
		self.duplicate_rows = sum(1 for row in staged if row["status"] == "Duplicate")
		self.error_rows = sum(1 for row in staged if row["status"] == "Error")
		self.imported_rows = 0
		self.skipped_rows = 0
		self.error_log = json.dumps(errors, indent=1) if errors else None

		return {
			"mapping_source": source,
			"header_row": header_row,
			"mapping": mapping,
			"total_rows": self.total_rows,
			"new_rows": self.new_rows,
			"duplicate_rows": self.duplicate_rows,
			"error_rows": self.error_rows,
		}

	def _capture_summary_balance(self, raw_row, mapping, opening, closing):
		"""Pull opening/closing balance out of a footer row instead of importing it."""
		text = " ".join(str(cell).casefold() for cell in raw_row if cell is not None)
		amounts = [parse_amount(cell) for cell in raw_row]
		amounts = [a for a in amounts if a is not None]
		if not amounts:
			return opening, closing

		if "opening balance" in text and opening is None:
			opening = amounts[-1]
		elif "closing balance" in text and closing is None:
			closing = amounts[-1]

		return opening, closing

	def _parse_row(self, raw_row: list, mapping: dict, dayfirst: bool) -> dict | None:
		fmt = self.get_statement_format()
		transforms = (
			{row.target_field: row.transform for row in fmt.mappings} if fmt else {}
		)

		def cell(target):
			index = mapping.get(target)
			if index is None or index < 0 or index >= len(raw_row):
				return None
			return _apply_transform(raw_row[index], transforms.get(target))

		posting_date = parse_date(cell("posting_date") or cell("value_date"), dayfirst=dayfirst)
		if not posting_date:
			# No date means this is not a transaction row - blank separators, page
			# headers repeated mid-file, and so on.
			return None

		debit = parse_amount(cell("debit"))
		credit = parse_amount(cell("credit"))
		amount_value = parse_amount(cell("amount"))
		indicator = str(cell("dr_cr_indicator") or "").strip().casefold()

		direction, amount, error = _resolve_direction(debit, credit, amount_value, indicator)

		return {
			"posting_date": posting_date,
			"value_date": parse_date(cell("value_date"), dayfirst=dayfirst),
			"description": str(cell("description") or "").strip(),
			"reference_number": str(cell("reference_number") or "").strip() or None,
			"counterparty": str(cell("counterparty") or "").strip() or None,
			"debit": abs(debit) if debit else None,
			"credit": abs(credit) if credit else None,
			"balance_after": parse_amount(cell("balance_after")),
			"direction": direction,
			"amount": amount,
			"status": "Error" if error else "New",
			"message": error,
			"error": error,
		}

	def _apply_categories(self, staged: list[dict], rules: list[dict]) -> None:
		for row in staged:
			if row["status"] == "Error":
				continue
			match = categorize(
				{
					"description": row.get("description"),
					"counterparty": row.get("counterparty"),
					"reference_number": row.get("reference_number"),
					"direction": row.get("direction"),
					"amount": row.get("amount"),
					"account": self.account,
					"owner": self.owner,
				},
				rules,
			)
			row["category"] = match.get("category")
			if match.get("counterparty") and not row.get("counterparty"):
				row["counterparty"] = match["counterparty"]

	def _apply_dedup(self, staged: list[dict]) -> None:
		"""Fingerprint every row, then check the whole file against the database at once.

		One batched query for the file, not one per row - a year of statements is a few
		hundred rows and this keeps preview snappy.
		"""
		seen_in_file: set[str] = set()

		# Occurrence ordinals for the weakest dedup tier (no reference number, no running
		# balance) must count rows *within this file* as well as those already stored.
		# Deriving them from a database count alone gave two identical rows in the same
		# statement the same ordinal, the same hash, and silently dropped the second.
		occurrences: dict[tuple, int] = {}

		for row in staged:
			if row["status"] == "Error":
				continue

			signed = flt(row["amount"]) if row["direction"] == "In" else -flt(row["amount"])
			occurrence = None

			if not row.get("reference_number") and row.get("balance_after") is None:
				key = content_key(self.account, row["posting_date"], signed, row.get("description"))
				if key not in occurrences:
					occurrences[key] = occurrence_index(*key)
				occurrence = occurrences[key]
				occurrences[key] += 1

			row["dedup_hash"] = build_dedup_hash(
				account=self.account,
				posting_date=row["posting_date"],
				signed_amount=signed,
				description=row.get("description"),
				reference_number=row.get("reference_number"),
				balance_after=row.get("balance_after"),
				occurrence=occurrence,
			)

		hashes = [row["dedup_hash"] for row in staged if row.get("dedup_hash")]
		existing = set()
		for chunk in _chunks(hashes, 500):
			existing.update(
				frappe.get_all(
					"Wallet Transaction",
					filters={"dedup_hash": ["in", chunk], "account": self.account},
					pluck="dedup_hash",
				)
			)

		for row in staged:
			fingerprint = row.get("dedup_hash")
			if not fingerprint:
				continue

			if fingerprint in existing or fingerprint in seen_in_file:
				row["status"] = "Duplicate"
				row["message"] = _("Already imported.")
			else:
				seen_in_file.add(fingerprint)

	# ------------------------------------------------------------------ commit
	def commit_rows(self) -> dict:
		"""Create a Wallet Transaction for every row still marked New."""
		self.status = "Importing"
		self.save(ignore_permissions=True)

		imported = failed = 0

		# See WalletTransaction.refresh_account_balance: without this every inserted row
		# triggers a full SUM over the account, making a 5,000 row import quadratic.
		frappe.flags.wallet_bulk_import = True

		try:
			imported, failed = self._insert_rows()
		finally:
			# A leaked flag would silently stop balance refreshes for the rest of the request.
			frappe.flags.wallet_bulk_import = False

		refresh_cached_balance(self.account)
		return self._finish_commit(imported, failed)

	def _insert_rows(self) -> tuple[int, int]:
		imported = failed = 0

		for row in self.rows:
			if row.status != "New":
				continue

			savepoint = f"wallet_row_{row.idx}"
			frappe.db.savepoint(savepoint)
			try:
				transaction = frappe.get_doc(
					{
						"doctype": "Wallet Transaction",
						"account": self.account,
						"posting_date": row.posting_date,
						"value_date": row.value_date,
						"direction": row.direction,
						"amount": row.amount,
						"description": row.description,
						"counterparty": row.counterparty,
						"category": row.category,
						"reference_number": row.reference_number,
						"balance_after": row.balance_after,
						"source": "Statement Import",
						"statement_import": self.name,
					}
				).insert()
				row.transaction = transaction.name
				row.status = "Imported"
				row.message = None
				imported += 1
			except frappe.UniqueValidationError:
				frappe.db.rollback(save_point=savepoint)
				row.status = "Duplicate"
				row.message = _("Already imported.")
			except Exception as e:
				frappe.db.rollback(save_point=savepoint)
				row.status = "Error"
				row.message = str(e)[:500]
				failed += 1

		# Recompute from the child table rather than from this call's counter: on a retry
		# of a partially completed import, `imported` holds only the rows this call
		# created, and the document would report fewer than it actually contains.
		return imported, failed

	def _finish_commit(self, imported: int, failed: int) -> dict:
		self.imported_rows = sum(1 for row in self.rows if row.status == "Imported")
		self.error_rows = sum(1 for row in self.rows if row.status == "Error")
		self.duplicate_rows = sum(1 for row in self.rows if row.status == "Duplicate")
		self.new_rows = sum(1 for row in self.rows if row.status == "New")
		self.skipped_rows = sum(1 for row in self.rows if row.status == "Skipped")
		self.status = "Partially Completed" if failed else "Completed"

		self.reconcile()
		self.save(ignore_permissions=True)
		frappe.db.commit()

		return {
			"imported": imported,
			"failed": failed,
			"duplicates": self.duplicate_rows,
			"variance": self.balance_variance,
		}

	def reconcile(self) -> None:
		"""Compare our computed balance against the balance the statement itself states.

		This is the one number that checks parsing, sign convention and deduplication all
		at once: if a row was missed, double counted or read from the wrong column, the
		variance is non-zero.
		"""
		if not self.period_to:
			return

		from wallet.api.balance import get_account_balance

		self.computed_closing_balance = get_account_balance(self.account, str(self.period_to))["balance"]

		if self.statement_closing_balance is None:
			self.balance_variance = None
			return

		self.balance_variance = flt(self.computed_closing_balance) - flt(self.statement_closing_balance)


# ---------------------------------------------------------------------- helpers
def _resolve_direction(
	debit: float | None, credit: float | None, amount: float | None, indicator: str
) -> tuple[str | None, float | None, str | None]:
	"""Work out In/Out and a positive magnitude from whichever convention the bank used."""
	if debit and credit:
		return None, None, _("Row has both a debit and a credit amount.")

	if debit:
		return "Out", abs(debit), None
	if credit:
		return "In", abs(credit), None

	if amount is not None and amount != 0:
		if indicator:
			if indicator.startswith("c"):
				return "In", abs(amount), None
			if indicator.startswith("d"):
				return "Out", abs(amount), None
		# A single signed amount column: negative is money leaving.
		return ("In", amount, None) if amount > 0 else ("Out", abs(amount), None)

	return None, None, _("Row has no amount.")


def _last_running_balance(staged: list[dict]) -> float | None:
	for row in reversed(staged):
		if row.get("balance_after") is not None:
			return row["balance_after"]
	return None


def _apply_transform(value, transform: str | None):
	"""Per-column cleanup a saved format asks for."""
	if not transform or transform == "None" or value is None:
		return value

	if transform == "Strip":
		return str(value).strip()
	if transform == "Uppercase":
		return str(value).strip().upper()
	if transform == "Absolute":
		from wallet.statement.parse import parse_amount

		amount = parse_amount(value)
		return abs(amount) if amount is not None else value

	return value


def _jsonable(value):
	if value is None or isinstance(value, str | int | float | bool):
		return value
	return str(value)


def _chunks(items: list, size: int):
	for start in range(0, len(items), size):
		yield items[start : start + size]
