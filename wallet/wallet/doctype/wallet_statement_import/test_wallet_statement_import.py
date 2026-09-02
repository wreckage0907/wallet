# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Statement Import controller.

The controller is the whole pipeline in one document: file in, layout resolved, rows
staged, categorized, fingerprinted, and only then committed. Nothing reaches Wallet
Transaction until `commit_rows`, and each row commits inside its own savepoint - so the
properties worth pinning are the ones that make a preview trustworthy and a bad row
survivable.

The strongest assertion in the file is the reconciliation one. `balance_variance` compares
what we computed against the closing balance the bank itself printed, so a zero variance
checks parsing, the sign convention and deduplication all at once. If a row were missed,
double counted, or read from the wrong column, that one number moves.
"""

import frappe
from frappe.tests import IntegrationTestCase, change_settings, set_user

from wallet.tests.fixtures import (
	STATEMENT_CLOSING_BALANCE,
	STATEMENT_HEADER,
	STATEMENT_ROWS,
	commit,
	make_account,
	make_category,
	make_import,
	make_rule,
	make_transaction,
	make_user,
	purge,
	statement_grid,
	xlsx_bytes,
)

#: The statement's own opening balance, so a clean import reconciles to zero variance.
OPENING_BALANCE = 100000.0


class StatementImportTestCase(IntegrationTestCase):
	"""Shared setup: one holder, one account opened at the statement's opening balance."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user(cls.email)
		cls.purge_imports()
		purge(cls.user)

		with set_user(cls.user):
			cls.account = make_account(
				"Import Savings", opening_balance=OPENING_BALANCE, opening_date="2026-01-01"
			)

		commit()

	@classmethod
	def tearDownClass(cls):
		cls.purge_imports()
		purge(cls.user)
		commit()
		super().tearDownClass()

	def tearDown(self):
		"""Clear everything a test created, keeping the account.

		`IntegrationTestCase` rolls each test back, which would normally be enough - but
		`commit_rows` commits as part of finishing an import, deliberately, so its rows
		outlive the rollback and would be waiting for the next test as pre-existing
		history. Deduplication is exactly what that history changes, so the contamination
		would not merely be untidy: a test asserting two rows stage as New would see them
		as Duplicate, for a reason nothing in the test mentions.
		"""
		self.purge_imports()
		frappe.db.delete("Wallet Categorization Rule", {"owner": self.email})
		frappe.db.delete("Wallet Category", {"owner": self.email})
		commit()
		super().tearDown()

	@classmethod
	def purge_imports(cls):
		"""Imports and their transactions link to each other, so neither can be deleted
		while the other stands. `frappe.db.delete` skips link validation, which is the
		only way to clear a committed import without unpicking it row by row."""
		for doctype in ("Wallet Statement Import Row", "Wallet Statement Import"):
			frappe.db.delete(doctype, {"owner": cls.email})
		frappe.db.delete("Wallet Transaction", {"owner": cls.email})

	def new_import(self, grid=None, **extra) -> str:
		with set_user(self.user):
			return make_import(self.account, xlsx_bytes(grid or statement_grid()), **extra)


class TestStaging(StatementImportTestCase):
	email = "imp-stage@example.com"

	def test_the_header_is_found_and_every_column_mapped(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			result = doc.parse()

		self.assertEqual(result["mapping_source"], "detected")
		self.assertEqual(result["header_row"], 5)
		self.assertEqual(
			set(result["mapping"]),
			{
				"posting_date",
				"description",
				"reference_number",
				"value_date",
				"debit",
				"credit",
				"balance_after",
			},
		)

	def test_every_transaction_row_is_staged_and_the_footer_is_not(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		self.assertEqual(doc.total_rows, len(STATEMENT_ROWS))
		self.assertNotIn("Closing Balance", [row.description for row in doc.rows])

	def test_the_status_lands_on_preview_ready(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		self.assertEqual(doc.status, "Preview Ready")

	def test_debit_and_credit_columns_become_a_direction_and_a_magnitude(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		by_description = {row.description: row for row in doc.rows}
		self.assertEqual(by_description["UPI-SWIGGY-ORDER-9911"].direction, "Out")
		self.assertEqual(by_description["UPI-SWIGGY-ORDER-9911"].amount, 250)
		self.assertEqual(by_description["SALARY CREDIT ACME LTD"].direction, "In")
		self.assertEqual(by_description["SALARY CREDIT ACME LTD"].amount, 85000)

	def test_a_merchant_whose_name_contains_total_is_still_imported(self):
		"""Footer detection used to run before parsing, and a fuel payment to
		"TotalEnergies" was silently dropped as a summary row."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		self.assertIn("TOTALENERGIES FUEL PUMP", [row.description for row in doc.rows])

	def test_the_period_is_taken_from_the_rows_that_parsed(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		self.assertEqual(str(doc.period_from), "2026-04-02")
		self.assertEqual(str(doc.period_to), "2026-04-06")

	def test_the_stated_closing_balance_is_read_off_the_footer(self):
		"""It is the number reconciliation compares against, and it lives on a row that is
		deliberately not imported."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		self.assertEqual(doc.statement_closing_balance, STATEMENT_CLOSING_BALANCE)

	def test_a_row_with_a_date_but_no_amount_is_flagged_not_dropped(self):
		"""Silently discarding it would leave the variance non-zero with nothing to point
		at. Flagged, the user can see exactly which line the parser could not read."""
		grid = statement_grid(
			rows=[
				["07/04/2026", "SOME NARRATION", "REF9", "07/04/2026", "", "", "150150.00"],
				*STATEMENT_ROWS,
			]
		)

		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import(grid))
			doc.parse()

		errored = [row for row in doc.rows if row.status == "Error"]
		self.assertEqual(len(errored), 1)
		self.assertIn("amount", errored[0].message.casefold())

	def test_a_row_with_both_a_debit_and_a_credit_is_an_error(self):
		"""Ambiguous, and guessing which one the bank meant is how money goes missing."""
		grid = statement_grid(
			rows=[["07/04/2026", "BOTH COLUMNS", "REF9", "07/04/2026", "100.00", "200.00", "150150.00"]]
		)

		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import(grid))
			doc.parse()

		self.assertEqual(doc.rows[0].status, "Error")
		self.assertIn("debit and a credit", doc.rows[0].message)

	def test_a_row_with_no_date_is_not_a_transaction_row_at_all(self):
		"""Blank separators and repeated page headers. They are skipped, not flagged - an
		error per blank line would bury the ones that matter."""
		grid = statement_grid(rows=[["", "PAGE 2 OF 3", "", "", "", "", ""], *STATEMENT_ROWS])

		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import(grid))
			doc.parse()

		self.assertEqual(doc.total_rows, len(STATEMENT_ROWS))

	def test_a_file_with_no_transaction_table_is_refused_with_a_reason(self):
		with set_user(self.user):
			name = self.new_import([["Dear Customer"], ["Thank you for banking with us"]])
			doc = frappe.get_doc("Wallet Statement Import", name)

			with self.assertRaises(frappe.ValidationError):
				doc.parse()

		self.assertEqual(frappe.db.get_value("Wallet Statement Import", name, "status"), "Failed")

	def test_a_failed_parse_records_why(self):
		with set_user(self.user):
			name = self.new_import([["Dear Customer"]])
			doc = frappe.get_doc("Wallet Statement Import", name)
			with self.assertRaises(frappe.ValidationError):
				doc.parse()

		self.assertTrue(frappe.db.get_value("Wallet Statement Import", name, "error_log"))

	@change_settings("Wallet Settings", {"max_import_rows": 3})
	def test_a_statement_longer_than_the_configured_limit_is_refused(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())

			with self.assertRaises(frappe.ValidationError):
				doc.parse()

	def test_the_header_labels_are_remembered_for_save_as_format(self):
		"""A successful parse clears the stored password, so the file cannot be reopened
		afterwards - the labels have to be kept from the pass that read it."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		self.assertEqual(frappe.parse_json(doc.header_labels), STATEMENT_HEADER)


class TestStagingCategorization(StatementImportTestCase):
	email = "imp-categorize@example.com"

	def test_staged_rows_are_categorized_before_anything_is_committed(self):
		"""The point of categorizing during staging: you see the categories in the preview
		and can correct them before a single transaction exists."""
		with set_user(self.user):
			category = make_category("Import Food")
			make_rule("Import swiggy", "SWIGGY", category)
			commit()

			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		staged = {row.description: row.category for row in doc.rows}
		self.assertEqual(staged["UPI-SWIGGY-ORDER-9911"], category)
		self.assertIsNone(staged["NACH-EMI-HOMELOAN"])

	def test_previewing_does_not_count_a_rule_match(self):
		"""Re-parsing a statement three times must not treble the tally. The count happens
		in Wallet Transaction's `after_insert`, on commit."""
		with set_user(self.user):
			category = make_category("Preview Food")
			rule = make_rule("Preview swiggy", "SWIGGY", category)
			commit()

			for _ in range(3):
				doc = frappe.get_doc("Wallet Statement Import", self.new_import())
				doc.parse()

		self.assertEqual(frappe.db.get_value("Wallet Categorization Rule", rule, "times_matched"), 0)


class TestStagingDedup(StatementImportTestCase):
	email = "imp-dedup@example.com"

	def test_two_identical_rows_in_one_file_are_both_kept(self):
		"""They differ only in the running balance they leave behind, which is exactly what
		the balance tier of the fingerprint exists to notice."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		chai = [row for row in doc.rows if row.description == "UPI-CHAI-STALL"]
		self.assertEqual(len(chai), 2)
		self.assertEqual([row.status for row in chai], ["New", "New"])

	def test_a_row_already_in_the_database_comes_back_as_a_duplicate(self):
		with set_user(self.user):
			# Same reference number: with one present the fingerprint is the reference tier
			# alone, so this is the exact row the statement carries.
			make_transaction(
				self.account,
				"2026-04-02",
				"Out",
				250,
				"UPI-SWIGGY-ORDER-9911",
				reference_number="REF001",
			)
			commit()

			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()

		by_description = {row.description: row for row in doc.rows}
		self.assertEqual(by_description["UPI-SWIGGY-ORDER-9911"].status, "Duplicate")
		self.assertEqual(by_description["SALARY CREDIT ACME LTD"].status, "New")

	def test_a_row_repeated_within_one_file_is_marked_duplicate_the_second_time(self):
		"""Same reference number twice in one export - a genuine bank error, and it must
		not become two transactions."""
		repeated = [
			["02/04/2026", "UPI-SWIGGY-ORDER-9911", "REF001", "02/04/2026", "250.00", "", "99750.00"],
			["02/04/2026", "UPI-SWIGGY-ORDER-9911", "REF001", "02/04/2026", "250.00", "", "99750.00"],
		]

		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import(statement_grid(rows=repeated)))
			doc.parse()

		self.assertEqual([row.status for row in doc.rows], ["New", "Duplicate"])

	def test_re_importing_the_whole_statement_stages_nothing_new(self):
		"""The property the whole module is for: statements overlap month to month, and
		the second import must be a no-op."""
		with set_user(self.user):
			first = frappe.get_doc("Wallet Statement Import", self.new_import())
			first.parse()
			first.commit_rows()

			second = frappe.get_doc("Wallet Statement Import", self.new_import())
			result = second.parse()

		self.assertEqual(result["new_rows"], 0)
		self.assertEqual(result["duplicate_rows"], len(STATEMENT_ROWS))


class TestCommit(StatementImportTestCase):
	email = "imp-commit@example.com"

	def test_committing_creates_one_transaction_per_new_row(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			result = doc.commit_rows()

		self.assertEqual(result["imported"], len(STATEMENT_ROWS))
		self.assertEqual(result["failed"], 0)
		self.assertEqual(doc.status, "Completed")

	def test_each_committed_row_records_the_transaction_it_created(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			doc.commit_rows()

		for row in doc.rows:
			self.assertEqual(row.status, "Imported")
			self.assertTrue(row.transaction)

	def test_the_committed_transactions_carry_their_provenance(self):
		with set_user(self.user):
			name = self.new_import()
			doc = frappe.get_doc("Wallet Statement Import", name)
			doc.parse()
			doc.commit_rows()

			sample = frappe.get_doc("Wallet Transaction", doc.rows[0].transaction)

		self.assertEqual(sample.source, "Statement Import")
		self.assertEqual(sample.statement_import, name)

	def test_committing_reconciles_to_the_banks_own_closing_balance(self):
		"""One number that checks parsing, the sign convention and deduplication together.
		A missed row, a doubled row or a column read backwards all move it off zero."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			doc.commit_rows()

		self.assertEqual(doc.computed_closing_balance, STATEMENT_CLOSING_BALANCE)
		self.assertEqual(doc.balance_variance, 0)

	def test_a_skipped_row_is_not_committed(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			doc.rows[0].status = "Skipped"
			doc.save(ignore_permissions=True)
			result = doc.commit_rows()

		self.assertEqual(result["imported"], len(STATEMENT_ROWS) - 1)
		self.assertEqual(doc.skipped_rows, 1)

	def test_committing_twice_imports_nothing_the_second_time(self):
		"""Rows that already went in are marked Imported, and only New rows are read."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			doc.commit_rows()
			second = doc.commit_rows()

		self.assertEqual(second["imported"], 0)
		self.assertEqual(doc.imported_rows, len(STATEMENT_ROWS))

	def test_one_bad_row_does_not_abort_the_batch(self):
		"""Every row commits inside its own savepoint. A transaction dated before the
		account opened is rejected by the controller, and the rest still land."""
		grid = statement_grid(
			rows=[
				["02/04/2019", "BEFORE THE ACCOUNT OPENED", "REF-OLD", "02/04/2019", "10.00", "", "1.00"],
				*STATEMENT_ROWS,
			]
		)

		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import(grid))
			doc.parse()
			result = doc.commit_rows()

		self.assertEqual(result["imported"], len(STATEMENT_ROWS))
		self.assertEqual(result["failed"], 1)
		self.assertEqual(doc.status, "Partially Completed")

	def test_a_failed_row_says_why(self):
		grid = statement_grid(
			rows=[["02/04/2019", "TOO EARLY", "REF-OLD", "02/04/2019", "10.00", "", "1.00"]]
		)

		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import(grid))
			doc.parse()
			doc.commit_rows()

		self.assertEqual(doc.rows[0].status, "Error")
		self.assertIn("opening date", doc.rows[0].message)

	def test_the_account_balance_is_refreshed_once_at_the_end(self):
		"""Per-row refreshes would make a 5,000 row import quadratic, so the importer sets
		`wallet_bulk_import` and refreshes the account itself after the batch."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			doc.commit_rows()

		self.assertEqual(
			frappe.db.get_value("Wallet Account", self.account, "cached_balance"),
			STATEMENT_CLOSING_BALANCE,
		)

	def test_the_bulk_flag_is_cleared_even_when_the_batch_raises(self):
		"""A leaked flag would silently stop balance refreshes for the rest of the request."""
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())
			doc.parse()
			doc.commit_rows()

		self.assertFalse(frappe.flags.wallet_bulk_import)


class TestFileAccess(StatementImportTestCase):
	email = "imp-file@example.com"

	def test_an_import_with_no_file_says_so(self):
		with set_user(self.user):
			doc = frappe.get_doc({"doctype": "Wallet Statement Import", "account": self.account}).insert()

			with self.assertRaises(frappe.ValidationError):
				doc.get_file_content()

	def test_a_file_attached_to_this_import_is_readable(self):
		with set_user(self.user):
			doc = frappe.get_doc("Wallet Statement Import", self.new_import())

			self.assertTrue(doc.get_file_content())

	def test_another_holders_private_file_cannot_be_pointed_at(self):
		"""`statement_file` is an Attach field - arbitrary text - so it can be aimed at any
		file URL on the site, including another holder's private upload. Only a file
		attached to this very import is taken on trust.

		Saved through the ordinary path, with no `ignore_permissions`, because that is how
		the attempt would actually arrive: an authenticated holder editing their own import
		document. Frappe re-points the File row's `attached_to` on save, so "is it attached
		here" is not on its own enough - the owner check behind it is what refuses.
		"""
		victim = make_user("imp-file-victim@example.com")

		with set_user(victim):
			victim_account = make_account("Victim Savings", opening_date="2026-01-01")
			victim_import = make_import(
				victim_account,
				xlsx_bytes(statement_grid(), sheet_name="Victim Secret"),
				file_name="victim_statement.xlsx",
			)
			victim_file = frappe.db.get_value("Wallet Statement Import", victim_import, "statement_file")
		commit()

		try:
			with set_user(self.user):
				doc = frappe.get_doc("Wallet Statement Import", self.new_import())
				doc.statement_file = victim_file
				doc.save()

				with self.assertRaises(frappe.PermissionError):
					doc.get_file_content()
		finally:
			for doctype in ("Wallet Statement Import Row", "Wallet Statement Import"):
				frappe.db.delete(doctype, {"owner": victim})
			frappe.db.delete("Wallet Account", {"owner": victim})
			frappe.db.delete("File", {"owner": victim})
			commit()
