# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.api.import_api`.

The whitelisted surface of the import wizard. What is genuinely this module's own, rather
than the controller's, is input validation and access control - so that is what these
tests are about.

`normalize_mapping` gets the most cases because a mapping arrives straight off the wire.
Checking only that it was a non-empty object was not enough: a mapping with no date column
crashed the stager on a `None` comparison, and a negative index read silently from the
wrong end of the row through Python's negative indexing.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.api import import_api
from wallet.tests.fixtures import (
	STATEMENT_HEADER,
	STATEMENT_ROWS,
	commit,
	make_account,
	make_bank,
	make_import,
	make_user,
	purge,
	statement_grid,
	xlsx_bytes,
)


class TestNormalizeMapping(IntegrationTestCase):
	def valid(self) -> dict:
		return {"posting_date": 0, "description": 1, "debit": 4, "credit": 5}

	def test_a_valid_mapping_comes_back_with_integer_indexes(self):
		"""A form-encoded POST delivers every value as a string."""
		cleaned = import_api.normalize_mapping({"posting_date": "0", "amount": "3"})

		self.assertEqual(cleaned, {"posting_date": 0, "amount": 3})

	def test_a_json_string_is_accepted(self):
		"""The browser sends the mapping as a JSON string, not an object, so a bare `dict`
		annotation would reject every real request."""
		self.assertEqual(
			import_api.normalize_mapping(json.dumps(self.valid())),
			self.valid(),
		)

	def test_an_unknown_target_field_is_refused(self):
		"""Anything outside the allowed set is a typo or an attempt to write a field the
		wizard was never meant to reach."""
		with self.assertRaises(frappe.ValidationError):
			import_api.normalize_mapping({"posting_date": 0, "amount": 3, "owner": 9})

	def test_a_non_numeric_index_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			import_api.normalize_mapping({"posting_date": 0, "amount": "the third one"})

	def test_a_negative_index_is_refused(self):
		"""Python indexes backwards from the end, so -1 would silently read the running
		balance column as the date."""
		with self.assertRaises(frappe.ValidationError):
			import_api.normalize_mapping({"posting_date": 0, "amount": -1})

	def test_a_mapping_with_no_date_column_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			import_api.normalize_mapping({"description": 1, "amount": 3})

	def test_a_mapping_with_no_amount_column_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			import_api.normalize_mapping({"posting_date": 0, "description": 1})

	def test_an_empty_mapping_is_refused(self):
		for mapping in ({}, "{}", "[]"):
			with self.subTest(mapping=mapping), self.assertRaises(frappe.ValidationError):
				import_api.normalize_mapping(mapping)

	def test_malformed_json_raises_the_decoders_error_rather_than_a_readable_one(self):
		"""Known rough edge, pinned so a fix is deliberate.

		`frappe.parse_json` hands the string straight to orjson, so a truncated or
		hand-mangled payload surfaces as `JSONDecodeError` rather than as one of this
		module's own messages. Only reachable from a malformed client - the wizard always
		sends `JSON.stringify` output - which is why it is documented rather than guarded.
		"""
		with self.assertRaises(Exception) as caught:
			import_api.normalize_mapping("not json at all")

		self.assertNotIsInstance(caught.exception, frappe.ValidationError)

	def test_either_date_column_satisfies_the_date_requirement(self):
		self.assertIn("value_date", import_api.normalize_mapping({"value_date": 3, "amount": 3}))

	def test_any_of_the_three_amount_columns_satisfies_the_amount_requirement(self):
		for target in ("debit", "credit", "amount"):
			with self.subTest(target=target):
				cleaned = import_api.normalize_mapping({"posting_date": 0, target: 4})

				self.assertIn(target, cleaned)


class ImportApiTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user(cls.email)
		cls.intruder = make_user("api-intruder@example.com")
		cls.purge_all()

		with set_user(cls.user):
			cls.account = make_account("Api Savings", opening_balance=100000, opening_date="2026-01-01")
		with set_user(cls.intruder):
			cls.intruder_account = make_account("Api Intruder Savings", opening_date="2026-01-01")

		commit()

	@classmethod
	def tearDownClass(cls):
		cls.purge_all()
		commit()
		super().tearDownClass()

	@classmethod
	def purge_all(cls):
		for user in (cls.email, "api-intruder@example.com"):
			for doctype in (
				"Wallet Statement Import Row",
				"Wallet Statement Import",
				"Wallet Transaction",
			):
				frappe.db.delete(doctype, {"owner": user})
			purge(user)
		frappe.db.delete("Wallet Statement Format", {"format_name": ["like", "Api %"]})

	def tearDown(self):
		"""`commit_import` commits, deliberately, so its rows would outlive the framework's
		per-test rollback and change what the next test's deduplication sees."""
		for doctype in ("Wallet Statement Import Row", "Wallet Statement Import", "Wallet Transaction"):
			frappe.db.delete(doctype, {"owner": self.email})
		frappe.db.delete("Wallet Statement Format", {"format_name": ["like", "Api %"]})
		commit()
		super().tearDown()

	def new_import(self, grid=None) -> str:
		with set_user(self.user):
			return make_import(self.account, xlsx_bytes(grid or statement_grid()))


class TestParseAndPreview(ImportApiTestCase):
	email = "api-parse@example.com"

	def test_preview_layout_reports_the_header_it_found(self):
		"""It backs the correction screen: the user needs to see the real labels next to
		what we guessed."""
		with set_user(self.user):
			result = import_api.preview_layout(self.new_import())

		self.assertEqual(result["header_row"], 5)
		self.assertEqual(result["header"], STATEMENT_HEADER)
		self.assertEqual(result["mapping"]["posting_date"], 0)

	def test_preview_layout_returns_a_sample_of_the_rows(self):
		with set_user(self.user):
			result = import_api.preview_layout(self.new_import())

		self.assertEqual(len(result["sample"]), min(5, len(STATEMENT_ROWS)))
		self.assertEqual(result["sample"][0][1], STATEMENT_ROWS[0][1])

	def test_parse_statement_stages_the_rows(self):
		with set_user(self.user):
			result = import_api.parse_statement(self.new_import())

		self.assertEqual(result["total_rows"], len(STATEMENT_ROWS))
		self.assertEqual(result["new_rows"], len(STATEMENT_ROWS))

	def test_another_holder_cannot_parse_this_import(self):
		"""Every endpoint here goes through `_get_import`, which checks write permission
		before anything else happens."""
		name = self.new_import()

		with set_user(self.intruder), self.assertRaises(frappe.PermissionError):
			import_api.parse_statement(name)

	def test_another_holder_cannot_preview_this_import(self):
		name = self.new_import()

		with set_user(self.intruder), self.assertRaises(frappe.PermissionError):
			import_api.preview_layout(name)


class TestUpdateMapping(ImportApiTestCase):
	email = "api-mapping@example.com"

	def test_a_corrected_mapping_re_stages_the_rows(self):
		"""The fix for a mis-detected column is to correct the mapping and re-parse, never
		to hand-edit the staged values."""
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			result = import_api.update_mapping(
				name, {"posting_date": 0, "description": 1, "debit": 4, "credit": 5}
			)

		self.assertEqual(result["mapping_source"], "manual")
		self.assertEqual(result["total_rows"], len(STATEMENT_ROWS))

	def test_the_corrected_mapping_is_stored_on_the_import(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			import_api.update_mapping(name, {"posting_date": 0, "description": 1, "amount": 4})

		stored = frappe.parse_json(frappe.db.get_value("Wallet Statement Import", name, "detected_mapping"))
		self.assertEqual(stored, {"posting_date": 0, "description": 1, "amount": 4})

	def test_dropping_the_balance_column_changes_how_rows_deduplicate(self):
		"""Without a running balance the fingerprint falls to the occurrence ordinal, and
		the two identical chai rows have to stay distinct on that alone."""
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			import_api.update_mapping(name, {"posting_date": 0, "description": 1, "debit": 4, "credit": 5})
			doc = frappe.get_doc("Wallet Statement Import", name)

		chai = [row for row in doc.rows if row.description == "UPI-CHAI-STALL"]
		self.assertEqual([row.status for row in chai], ["New", "New"])

	def test_an_invalid_mapping_is_refused_before_anything_is_re_staged(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			before = frappe.db.get_value("Wallet Statement Import", name, "detected_mapping")

			with self.assertRaises(frappe.ValidationError):
				import_api.update_mapping(name, {"description": 1, "amount": 3})

		self.assertEqual(frappe.db.get_value("Wallet Statement Import", name, "detected_mapping"), before)

	def test_another_holder_cannot_re_map_this_import(self):
		name = self.new_import()

		with set_user(self.intruder), self.assertRaises(frappe.PermissionError):
			import_api.update_mapping(name, {"posting_date": 0, "amount": 3})


class TestSetRowStatus(ImportApiTestCase):
	email = "api-rows@example.com"

	def staged(self, name):
		return frappe.get_doc("Wallet Statement Import", name)

	def test_a_row_can_be_skipped_before_commit(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			index = self.staged(name).rows[0].row_index
			result = import_api.set_row_status(name, [{"row_index": index, "status": "Skipped"}])

		self.assertEqual(result["skipped_rows"], 1)
		self.assertEqual(result["new_rows"], len(STATEMENT_ROWS) - 1)

	def test_a_skipped_row_can_be_put_back(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			index = self.staged(name).rows[0].row_index
			import_api.set_row_status(name, [{"row_index": index, "status": "Skipped"}])
			result = import_api.set_row_status(name, [{"row_index": index, "status": "New"}])

		self.assertEqual(result["new_rows"], len(STATEMENT_ROWS))

	def test_an_error_row_can_be_reset_to_new(self):
		"""The retry path a Partially Completed import advertises. The child status is
		read-only in the form, so this is the only way back."""
		grid = statement_grid(
			rows=[["07/04/2026", "NO AMOUNT HERE", "REF9", "07/04/2026", "", "", "1.00"], *STATEMENT_ROWS]
		)
		name = self.new_import(grid)

		with set_user(self.user):
			import_api.parse_statement(name)
			errored = next(row for row in self.staged(name).rows if row.status == "Error")
			import_api.set_row_status(name, [{"row_index": errored.row_index, "status": "New"}])

			refreshed = next(row for row in self.staged(name).rows if row.row_index == errored.row_index)

		self.assertEqual(refreshed.status, "New")
		self.assertIsNone(refreshed.message)

	def test_a_category_can_be_assigned_to_a_staged_row(self):
		name = self.new_import()

		with set_user(self.user):
			from wallet.tests.fixtures import make_category

			category = make_category("Api Groceries")
			import_api.parse_statement(name)
			index = self.staged(name).rows[0].row_index
			import_api.set_row_status(name, [{"row_index": index, "category": category}])

			assigned = next(row for row in self.staged(name).rows if row.row_index == index)

		self.assertEqual(assigned.category, category)

	def test_an_imported_row_cannot_be_skipped_after_the_fact(self):
		"""Only rows still in play may change status; a committed row has a transaction
		behind it and skipping it would say otherwise."""
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			import_api.commit_import(name)
			index = self.staged(name).rows[0].row_index
			import_api.set_row_status(name, [{"row_index": index, "status": "Skipped"}])

			after = next(row for row in self.staged(name).rows if row.row_index == index)

		self.assertEqual(after.status, "Imported")

	def test_a_payload_that_is_not_a_list_is_refused(self):
		"""Reached with a JSON *string* that decodes to something else. A bare dict never
		gets this far: `require_type_annotated_api_methods` coerces arguments through
		pydantic first, and the declared `list[dict] | str` rejects it with a
		FrappeTypeError before the function is entered.
		"""
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)

			with self.assertRaises(frappe.ValidationError):
				import_api.set_row_status(name, '{"row_index": 6}')

	def test_a_bare_dict_is_rejected_by_the_annotation_layer(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)

			with self.assertRaises(frappe.exceptions.FrappeTypeError):
				import_api.set_row_status(name, {"row_index": 6})

	def test_a_json_string_payload_is_accepted(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			index = self.staged(name).rows[0].row_index
			result = import_api.set_row_status(name, json.dumps([{"row_index": index, "status": "Skipped"}]))

		self.assertEqual(result["skipped_rows"], 1)

	def test_another_holder_cannot_edit_these_rows(self):
		name = self.new_import()

		with set_user(self.intruder), self.assertRaises(frappe.PermissionError):
			import_api.set_row_status(name, [{"row_index": 6, "status": "Skipped"}])


class TestCommitImport(ImportApiTestCase):
	email = "api-commit@example.com"

	def test_committing_a_previewed_import_creates_the_transactions(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			result = import_api.commit_import(name)

		self.assertEqual(result["imported"], len(STATEMENT_ROWS))
		self.assertEqual(result["variance"], 0)

	def test_committing_before_parsing_is_refused(self):
		"""There is nothing staged, and the message says which step was skipped rather
		than reporting zero rows imported as a success."""
		name = self.new_import()

		with set_user(self.user), self.assertRaises(frappe.ValidationError):
			import_api.commit_import(name)

	def test_another_holder_cannot_commit_this_import(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)

		with set_user(self.intruder), self.assertRaises(frappe.PermissionError):
			import_api.commit_import(name)


class TestSaveAsFormat(ImportApiTestCase):
	email = "api-format@example.com"

	def test_the_mapping_is_remembered_against_the_bank(self):
		"""The point: the next statement from this bank skips the mapping step entirely."""
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			fmt = import_api.save_as_format(name, "Api HDFC Savings", make_bank("Api Bank"))

		doc = frappe.get_doc("Wallet Statement Format", fmt)
		self.assertEqual(doc.header_row, 5)
		self.assertEqual(doc.amount_convention, "Separate Debit/Credit Columns")
		self.assertEqual(doc.has_running_balance, 1)

	def test_the_saved_format_carries_the_real_column_labels(self):
		"""Read from the header captured during parse, not by reopening the file - a
		successful parse clears the password, so a re-read would fail on an encrypted
		statement."""
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			fmt = import_api.save_as_format(name, "Api HDFC Labels", make_bank("Api Bank"))

		labels = {
			row.target_field: row.column_label
			for row in frappe.get_doc("Wallet Statement Format", fmt).mappings
		}
		self.assertEqual(labels["posting_date"], "Date")
		self.assertEqual(labels["description"], "Narration")

	def test_the_format_is_adopted_onto_the_import(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)
			fmt = import_api.save_as_format(name, "Api HDFC Adopted", make_bank("Api Bank"))

		self.assertEqual(frappe.db.get_value("Wallet Statement Import", name, "statement_format"), fmt)

	def test_saving_a_format_before_parsing_is_refused(self):
		name = self.new_import()

		with set_user(self.user), self.assertRaises(frappe.ValidationError):
			import_api.save_as_format(name, "Api Too Early", make_bank("Api Bank"))

	def test_a_remembered_format_is_matched_by_its_header_signature(self):
		"""The one-click repeat import: same bank, same export, same signature, no
		mapping step."""
		first = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(first)
			import_api.save_as_format(first, "Api HDFC Repeat", make_bank("Api Bank"))
			commit()

			second = self.new_import()
			result = import_api.parse_statement(second)

		self.assertIn(result["mapping_source"], ("format", "remembered"))

	def test_another_holder_cannot_save_a_format_from_this_import(self):
		name = self.new_import()

		with set_user(self.user):
			import_api.parse_statement(name)

		with set_user(self.intruder), self.assertRaises(frappe.PermissionError):
			import_api.save_as_format(name, "Api Stolen", make_bank("Api Bank"))
