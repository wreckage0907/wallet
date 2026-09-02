# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.statement.detect`.

Pure functions over a grid of cells, so no database.

The grids below are shaped like the real thing: a block of branch and account-holder
detail, then the header, then transactions, then a summary footer. Header detection has to
find the middle band without being fooled by either end.
"""

from frappe.tests import UnitTestCase

from wallet.statement import detect

#: An HDFC-shaped export: junk block, header, rows, footer.
STATEMENT = [
	["HDFC BANK LTD"],
	["Account Holder", "JANE DOE"],
	["Address", "12 MG Road, Bengaluru"],
	["Statement Date", "01/04/2026"],
	[],
	["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
	["01/04/2026", "UPI-SWIGGY", "REF001", "01/04/2026", "250.00", "", "99,750.00"],
	["02/04/2026", "SALARY CREDIT", "REF002", "02/04/2026", "", "85,000.00", "1,84,750.00"],
	["", "Closing Balance", "", "", "", "", "1,84,750.00"],
]


class TestScoreRow(UnitTestCase):
	def test_a_header_row_maps_every_label_it_recognises(self):
		mapping = detect.score_row(STATEMENT[5])

		self.assertEqual(mapping["posting_date"], 0)
		self.assertEqual(mapping["description"], 1)
		self.assertEqual(mapping["reference_number"], 2)
		self.assertEqual(mapping["value_date"], 3)
		self.assertEqual(mapping["debit"], 4)
		self.assertEqual(mapping["credit"], 5)
		self.assertEqual(mapping["balance_after"], 6)

	def test_the_longer_keyword_wins(self):
		""" "Value Date" must not be claimed by the "date" keyword under posting_date."""
		mapping = detect.score_row(["Value Date", "Transaction Date"])

		self.assertEqual(mapping["value_date"], 0)
		self.assertEqual(mapping["posting_date"], 1)

	def test_the_first_column_to_claim_a_target_keeps_it(self):
		"""Statements repeat labels; the leftmost is the one the data sits under."""
		mapping = detect.score_row(["Date", "Narration", "Date"])

		self.assertEqual(mapping["posting_date"], 0)

	def test_labels_are_matched_regardless_of_case_and_punctuation(self):
		mapping = detect.score_row(["  TRANSACTION   DATE ", "PARTICULARS", "DEBIT AMT."])

		self.assertEqual(mapping["posting_date"], 0)
		self.assertEqual(mapping["description"], 1)
		self.assertEqual(mapping["debit"], 2)

	def test_blank_and_none_cells_map_to_nothing(self):
		self.assertEqual(detect.score_row([None, "", "   "]), {})


class TestIsUsable(UnitTestCase):
	def test_a_date_and_an_amount_are_enough(self):
		self.assertTrue(detect.is_usable({"posting_date": 0, "amount": 1}))
		self.assertTrue(detect.is_usable({"value_date": 0, "debit": 1}))
		self.assertTrue(detect.is_usable({"posting_date": 0, "credit": 1}))

	def test_a_date_alone_is_not(self):
		"""An address line containing the word "Date" would otherwise pass for a header."""
		self.assertFalse(detect.is_usable({"posting_date": 0, "description": 1}))

	def test_an_amount_alone_is_not(self):
		self.assertFalse(detect.is_usable({"debit": 0, "credit": 1}))

	def test_nothing_is_not(self):
		self.assertFalse(detect.is_usable({}))


class TestDetectHeader(UnitTestCase):
	def test_the_header_is_found_below_the_branch_detail_block(self):
		index, mapping = detect.detect_header(STATEMENT)

		self.assertEqual(index, 5)
		self.assertEqual(mapping["description"], 1)

	def test_the_richest_candidate_row_wins(self):
		"""Two rows qualify; the one naming more fields is the real header."""
		grid = [
			["Date", "Amount"],
			["Date", "Narration", "Withdrawal", "Deposit", "Balance"],
		]

		index, mapping = detect.detect_header(grid)

		self.assertEqual(index, 1)
		self.assertEqual(len(mapping), 5)

	def test_a_file_with_no_transaction_table_reports_minus_one(self):
		"""Returned, not raised - the caller turns it into a message the user can act on."""
		index, mapping = detect.detect_header([["Dear Customer"], ["Thank you for banking with us"]])

		self.assertEqual(index, -1)
		self.assertEqual(mapping, {})

	def test_only_the_leading_block_is_scanned(self):
		"""A header buried past the scan window is not worth finding, and looking for it
		over a 5,000 row statement is not free."""
		grid = [["filler"]] * 40 + [["Date", "Narration", "Amount"]]

		self.assertEqual(detect.detect_header(grid)[0], -1)
		self.assertEqual(detect.detect_header(grid, scan_rows=50)[0], 40)


class TestDetectAmountConvention(UnitTestCase):
	def test_separate_debit_and_credit_columns(self):
		self.assertEqual(
			detect.detect_amount_convention({"debit": 4, "credit": 5}),
			"Separate Debit/Credit Columns",
		)

	def test_one_amount_column_plus_an_indicator(self):
		self.assertEqual(
			detect.detect_amount_convention({"amount": 3, "dr_cr_indicator": 4}),
			"Amount + Dr/Cr Indicator",
		)

	def test_a_single_signed_amount_column(self):
		self.assertEqual(detect.detect_amount_convention({"amount": 3}), "Single Signed Amount")


class TestHeaderSignature(UnitTestCase):
	def test_the_same_header_signs_the_same(self):
		"""This is what makes a repeat import one click: same export, same signature,
		remembered format."""
		self.assertEqual(
			detect.header_signature(STATEMENT[5]),
			detect.header_signature(list(STATEMENT[5])),
		)

	def test_case_and_spacing_do_not_change_the_signature(self):
		"""Banks reformat their own headers between exports."""
		self.assertEqual(
			detect.header_signature(["Date", "Narration"]),
			detect.header_signature(["  DATE ", "narration"]),
		)

	def test_blank_cells_do_not_change_the_signature(self):
		"""Trailing empty columns are an artefact of the export, not of the layout."""
		self.assertEqual(
			detect.header_signature(["Date", "Narration"]),
			detect.header_signature(["Date", "", "Narration", None]),
		)

	def test_a_different_header_signs_differently(self):
		self.assertNotEqual(
			detect.header_signature(["Date", "Narration"]),
			detect.header_signature(["Date", "Particulars"]),
		)


class TestIsFooterRow(UnitTestCase):
	def test_summary_rows_are_recognised(self):
		for row in (
			["", "Closing Balance", "", "1,84,750.00"],
			["Opening Balance", "1,00,000.00"],
			["*** End of Statement ***"],
			["This is a computer generated statement"],
		):
			with self.subTest(row=row):
				self.assertTrue(detect.is_footer_row(row))

	def test_a_merchant_whose_name_contains_total_is_not_a_footer(self):
		"""The regression the narrow marker list exists for: a generic "total" marker
		swallowed real fuel payments to TotalEnergies."""
		self.assertFalse(detect.is_footer_row(["01/04/2026", "TOTALENERGIES FUEL", "2,500.00"]))

	def test_an_ordinary_transaction_row_is_not_a_footer(self):
		self.assertFalse(detect.is_footer_row(STATEMENT[6]))

	def test_a_blank_row_is_not_a_footer(self):
		self.assertFalse(detect.is_footer_row([]))
		self.assertFalse(detect.is_footer_row([None, "", "  "]))
