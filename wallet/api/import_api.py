# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Whitelisted endpoints for the statement import wizard.

Annotation note: `require_type_annotated_api_methods` is on, and values are coerced
through pydantic. Structured arguments must be annotated `dict | str` / `list[dict] | str`
and normalised with `frappe.parse_json`, because a form-encoded POST from the browser
delivers them as a JSON *string* and a bare `dict` annotation rejects it outright.
"""

import json

import frappe
from frappe import _

from wallet.statement import detect
from wallet.statement.reader import read_grid

#: Fields a column mapping may target. Anything else is a typo or an attack.
VALID_TARGETS = {
	"posting_date",
	"value_date",
	"description",
	"reference_number",
	"debit",
	"credit",
	"amount",
	"dr_cr_indicator",
	"balance_after",
	"counterparty",
}


def normalize_mapping(mapping: dict | str) -> dict[str, int]:
	"""Coerce and validate a target-field -> column-index mapping.

	Checking only that it is a non-empty object was not enough: a mapping with no date
	column crashed the stager on a None comparison, and a negative index silently read
	from the wrong end of the row via Python's negative indexing.
	"""
	mapping = frappe.parse_json(mapping)

	if not isinstance(mapping, dict) or not mapping:
		frappe.throw(_("Mapping must be an object of target field to column index."))

	cleaned: dict[str, int] = {}
	for target, index in mapping.items():
		if target not in VALID_TARGETS:
			frappe.throw(_("Unknown mapping target: {0}").format(target))
		try:
			column = int(index)
		except (TypeError, ValueError):
			frappe.throw(_("Column index for {0} must be a whole number.").format(target))
		if column < 0:
			frappe.throw(_("Column index for {0} cannot be negative.").format(target))
		cleaned[target] = column

	if not ({"posting_date", "value_date"} & cleaned.keys()):
		frappe.throw(_("The mapping needs a date column."))

	if not ({"debit", "credit", "amount"} & cleaned.keys()):
		frappe.throw(_("The mapping needs a debit, credit or amount column."))

	return cleaned


def _get_import(name: str):
	doc = frappe.get_doc("Wallet Statement Import", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist(methods=["POST"])
def parse_statement(
	name: str, password: str | None = None, statement_format: str | None = None
) -> dict:
	"""Read an attached statement and stage its rows for preview."""
	doc = _get_import(name)

	if statement_format:
		doc.statement_format = statement_format

	return doc.parse(password=password)


@frappe.whitelist(methods=["POST"])
def update_mapping(name: str, mapping: dict | str, password: str | None = None) -> dict:
	"""Override the detected column mapping and re-stage the rows.

	Used when the heuristic guessed a column wrong - the fix is to correct the mapping
	and re-parse, never to hand-edit the staged values.

	`password` has to be accepted again: re-staging means re-reading the file, and a
	successful parse deliberately clears the stored password, so an encrypted statement
	cannot be reopened without it.
	"""
	doc = _get_import(name)
	cleaned = normalize_mapping(mapping)

	doc.detected_mapping = json.dumps(cleaned, sort_keys=True)
	doc.save(ignore_permissions=True)

	grid, _sheet = read_grid(
		doc.get_file_content(),
		file_name=doc.statement_file,
		password=password or password_for(doc),
		sheet_name=doc.get_format_value("sheet_name"),
	)
	result = doc._stage_rows(grid, mapping_override=cleaned)
	doc.status = "Preview Ready"
	doc.save(ignore_permissions=True)
	return result


def password_for(doc) -> str | None:
	return doc.get_password("file_password", raise_exception=False)


@frappe.whitelist(methods=["POST"])
def set_row_status(name: str, updates: list[dict] | str) -> dict:
	"""Bulk-edit staged rows before commit: assign categories, skip rows.

	`updates` is a list of {"row_index": int, "category": str, "status": "Skipped"|"New"}.
	"""
	doc = _get_import(name)
	updates = frappe.parse_json(updates)

	if not isinstance(updates, list):
		frappe.throw(_("Updates must be a list."))

	by_index = {int(u["row_index"]): u for u in updates if u.get("row_index") is not None}
	changed = 0

	for row in doc.rows:
		update = by_index.get(row.row_index)
		if not update:
			continue

		if "category" in update:
			row.category = update["category"] or None
			changed += 1

		status = update.get("status")
		# Error rows must be resettable to New, otherwise the retry path that
		# commit_import advertises for a Partially Completed import can never import
		# anything - the child status is read-only, so this is the only way back.
		if status in ("Skipped", "New") and row.status in ("New", "Skipped", "Error"):
			row.status = status
			row.message = None if status == "New" else row.message
			changed += 1

	doc.new_rows = sum(1 for row in doc.rows if row.status == "New")
	doc.skipped_rows = sum(1 for row in doc.rows if row.status == "Skipped")
	doc.save(ignore_permissions=True)

	return {"changed": changed, "new_rows": doc.new_rows, "skipped_rows": doc.skipped_rows}


@frappe.whitelist(methods=["POST"])
def commit_import(name: str) -> dict:
	"""Create transactions from every staged row still marked New."""
	doc = _get_import(name)

	if doc.status not in ("Preview Ready", "Partially Completed"):
		frappe.throw(_("Nothing to import - parse the statement first."))

	return doc.commit_rows()


@frappe.whitelist(methods=["POST"])
def save_as_format(name: str, format_name: str, bank: str) -> str:
	"""Remember this import's column mapping, so the next statement from the same bank
	skips the mapping step entirely."""
	doc = _get_import(name)

	if not doc.detected_mapping:
		frappe.throw(_("Parse the statement before saving its format."))

	# Read from the header captured during parse rather than reopening the file: parse
	# clears the stored password, so re-reading an encrypted statement here would always
	# fail with a decryption error.
	mapping = frappe.parse_json(doc.detected_mapping)
	header = frappe.parse_json(doc.header_labels) if doc.header_labels else []

	fmt = frappe.get_doc(
		{
			"doctype": "Wallet Statement Format",
			"format_name": format_name,
			"bank": bank,
			"account_type": frappe.db.get_value("Wallet Account", doc.account, "account_type"),
			"file_type": "XLSX",
			"header_row": doc.header_row,
			"data_start_row": (doc.header_row or 0) + 1,
			"amount_convention": detect.detect_amount_convention(mapping),
			"has_running_balance": int("balance_after" in mapping),
			"header_signature": detect.header_signature(header),
			"mappings": [
				{
					"target_field": target,
					"column_index": index,
					"column_label": str(header[index]) if index < len(header) else None,
				}
				for target, index in sorted(mapping.items(), key=lambda item: item[1])
			],
		}
	)
	fmt.insert()

	doc.statement_format = fmt.name
	doc.save(ignore_permissions=True)

	return fmt.name


@frappe.whitelist(methods=["POST"])
def preview_layout(name: str, password: str | None = None) -> dict:
	"""Header row, detected mapping and the first rows of the file.

	POST, not GET: it takes a statement password, and a GET would put that secret in the
	URL - browser history, proxy logs, server access logs.

	Backs the mapping-correction screen: the user needs to see the actual header labels
	next to what we guessed.
	"""
	doc = _get_import(name)
	grid, sheet = read_grid(
		doc.get_file_content(), file_name=doc.statement_file, password=password or password_for(doc)
	)

	header_row, mapping = detect.detect_header(grid)
	header = grid[header_row] if header_row >= 0 else []

	return {
		"sheet": sheet,
		"header_row": header_row,
		"header": [str(cell) if cell is not None else "" for cell in header],
		"mapping": mapping,
		"sample": [
			[str(cell) if cell is not None else "" for cell in row]
			for row in grid[header_row + 1 : header_row + 6]
		],
	}
