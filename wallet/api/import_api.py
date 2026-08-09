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
def update_mapping(name: str, mapping: dict | str) -> dict:
	"""Override the detected column mapping and re-stage the rows.

	Used when the heuristic guessed a column wrong - the fix is to correct the mapping
	and re-parse, never to hand-edit the staged values.
	"""
	doc = _get_import(name)
	mapping = frappe.parse_json(mapping)

	if not isinstance(mapping, dict) or not mapping:
		frappe.throw(_("Mapping must be an object of target field to column index."))

	doc.detected_mapping = json.dumps({k: int(v) for k, v in mapping.items()}, sort_keys=True)
	doc.save(ignore_permissions=True)

	grid, _sheet = read_grid(
		doc.get_file_content(),
		file_name=doc.statement_file,
		password=password_for(doc),
	)
	result = doc._stage_rows(grid, mapping_override={k: int(v) for k, v in mapping.items()})
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
		if status in ("Skipped", "New") and row.status in ("New", "Skipped"):
			row.status = status
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

	grid, _sheet = read_grid(
		doc.get_file_content(), file_name=doc.statement_file, password=password_for(doc)
	)
	mapping = frappe.parse_json(doc.detected_mapping)
	header = grid[doc.header_row] if doc.header_row is not None and doc.header_row < len(grid) else []

	fmt = frappe.get_doc(
		{
			"doctype": "Wallet Statement Format",
			"format_name": format_name,
			"bank": bank,
			"account_type": frappe.db.get_value("Wallet Account", doc.account, "account_type"),
			"file_type": "XLSX",
			"header_row": doc.header_row,
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


@frappe.whitelist()
def preview_layout(name: str, password: str | None = None) -> dict:
	"""Header row, detected mapping and the first rows of the file.

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
