# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.statement.reader`.

The only module that knows about file formats. Everything downstream works on
`list[list[cell]]`, so what matters here is that each format arrives as the same shape and
that native types survive - openpyxl hands back real `datetime` and `float` objects, and
re-parsing those from strings would throw away information the bank gave us for free.

Files are built in memory by `wallet.tests.fixtures`; nothing here reads from disk. See
the repo convention: a real bank statement is the natural fixture and the easiest thing in
the world to commit by accident.
"""

import datetime

import frappe
from frappe.tests import IntegrationTestCase

from wallet.statement.reader import read_grid
from wallet.tests.fixtures import (
	STATEMENT_HEADER,
	STATEMENT_ROWS,
	csv_bytes,
	statement_grid,
	xlsx_bytes,
)


class TestReadGrid(IntegrationTestCase):
	"""`frappe.throw` needs a request context, so this runs as an integration test even
	though it touches no table."""

	def test_an_xlsx_comes_back_as_a_grid_with_its_sheet_name(self):
		grid, sheet = read_grid(xlsx_bytes(statement_grid(), sheet_name="April"), "statement.xlsx")

		self.assertEqual(sheet, "April")
		self.assertEqual([str(cell or "") for cell in grid[5]], STATEMENT_HEADER)

	def test_the_first_sheet_is_read_when_none_is_named(self):
		grid, sheet = read_grid(xlsx_bytes(statement_grid(), sheet_name="Only One"), "statement.xlsx")

		self.assertEqual(sheet, "Only One")
		self.assertTrue(grid)

	def test_a_named_sheet_is_honoured(self):
		import io

		import openpyxl

		workbook = openpyxl.Workbook()
		workbook.active.title = "Summary"
		workbook.active.append(["nothing here"])
		second = workbook.create_sheet("Transactions")
		for row in statement_grid():
			second.append(row)
		buffer = io.BytesIO()
		workbook.save(buffer)

		grid, sheet = read_grid(buffer.getvalue(), "statement.xlsx", sheet_name="Transactions")

		self.assertEqual(sheet, "Transactions")
		self.assertEqual([str(cell or "") for cell in grid[5]], STATEMENT_HEADER)

	def test_native_types_survive_the_read(self):
		"""The reason the pipeline works on cells rather than strings: a real date out of
		Excel never has to be guessed at, and `detect_dayfirst` skips it entirely."""
		grid, _ = read_grid(
			xlsx_bytes([["Date", "Amount"], [datetime.datetime(2026, 4, 1), 1234.56]]),
			"statement.xlsx",
		)

		self.assertIsInstance(grid[1][0], datetime.datetime)
		self.assertIsInstance(grid[1][1], float)

	def test_a_csv_is_read_by_its_extension(self):
		grid, sheet = read_grid(csv_bytes(statement_grid()), "statement.csv")

		self.assertEqual(sheet, "csv")
		self.assertEqual(grid[5], STATEMENT_HEADER)

	def test_every_delimiter_a_bank_might_use_is_sniffed(self):
		"""Banks emit comma, semicolon, tab and pipe separated files interchangeably, all
		of them named .csv."""
		rectangular = [STATEMENT_HEADER, *STATEMENT_ROWS]

		for delimiter in (",", ";", "\t", "|"):
			with self.subTest(delimiter=delimiter):
				grid, _ = read_grid(csv_bytes(rectangular, delimiter=delimiter), "statement.csv")

				self.assertEqual(grid[0], STATEMENT_HEADER)

	def test_a_ragged_leading_block_defeats_the_sniffer_on_anything_but_a_comma(self):
		"""Known limitation, pinned so a fix is deliberate rather than a surprise.

		`csv.Sniffer` infers the delimiter from the first 8KB, and a statement whose branch
		detail block has fewer columns than its transaction table gives it inconsistent
		evidence. It then falls back to `csv.excel`, every line becomes one cell, header
		detection finds nothing, and the user is told there is no transaction table in a
		file that plainly has one.

		Comma survives because it is the fallback. A semicolon or tab file with a ragged
		preamble does not, and that is the case worth knowing about: European and some
		Indian exports use semicolons.
		"""
		ragged = [["HDFC BANK LTD"], ["Account Holder", "JANE DOE"], STATEMENT_HEADER, *STATEMENT_ROWS]

		by_comma, _ = read_grid(csv_bytes(ragged, delimiter=","), "statement.csv")
		self.assertEqual(by_comma[2], STATEMENT_HEADER)

		for delimiter in (";", "\t"):
			with self.subTest(delimiter=delimiter):
				grid, _ = read_grid(csv_bytes(ragged, delimiter=delimiter), "statement.csv")

				self.assertEqual(len(grid[2]), 1)

	def test_a_byte_order_mark_is_stripped(self):
		"""Excel writes one on every CSV it exports, and it would otherwise ride along on
		the first header label and stop it matching any keyword."""
		content = b"\xef\xbb\xbf" + csv_bytes([["Date", "Narration"]])

		grid, _ = read_grid(content, "statement.csv")

		self.assertEqual(grid[0][0], "Date")

	def test_undecodable_bytes_do_not_abort_the_read(self):
		"""A statement that is 99% readable is worth reading. Latin-1 punctuation in an
		otherwise UTF-8 file is common and must not lose the whole file."""
		content = b"Date,Narration\n01/04/2026,CAF\xc9 PURCHASE\n"

		grid, _ = read_grid(content, "statement.csv")

		self.assertEqual(len(grid), 2)
		self.assertTrue(grid[1][1].startswith("CAF"))

	def test_a_file_with_no_extension_is_sniffed_by_its_first_bytes(self):
		"""An email attachment arrives named whatever the bank felt like."""
		grid, sheet = read_grid(csv_bytes([["Date", "Narration"]]), None)

		self.assertEqual(sheet, "csv")
		self.assertEqual(grid[0], ["Date", "Narration"])

	def test_an_extensionless_zip_is_read_as_a_workbook(self):
		"""An xlsx is a zip and begins with "PK", which is what the sniff keys on."""
		grid, sheet = read_grid(xlsx_bytes([["Date", "Narration"]]), None)

		self.assertNotEqual(sheet, "csv")
		self.assertEqual([str(cell) for cell in grid[0]], ["Date", "Narration"])

	def test_an_xlsx_misnamed_as_xls_is_still_read(self):
		"""Banks do this constantly. The routing checks the magic bytes, not the name."""
		grid, _ = read_grid(xlsx_bytes([["Date", "Narration"]]), "statement.xls")

		self.assertEqual([str(cell) for cell in grid[0]], ["Date", "Narration"])

	def test_something_that_is_not_a_workbook_throws_a_readable_message(self):
		"""A PDF statement, or a download that returned an error page. The user gets told
		what went wrong, not a traceback."""
		with self.assertRaises(frappe.ValidationError):
			read_grid(b"PK\x03\x04not really a workbook at all", "statement.xlsx")
