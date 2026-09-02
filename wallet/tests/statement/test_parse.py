# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.statement.parse`.

Pure functions over cell values, so no database - see `specs/testing.md`.

The cases here are drawn from what Indian bank exports actually contain: `Dr`/`Cr`
suffixes, accounting parentheses, dd/mm dates that only a column-wide look can tell from
mm/dd, and two-digit years.
"""

import datetime

from frappe.tests import UnitTestCase

from wallet.statement.parse import detect_dayfirst, parse_amount, parse_date


class TestParseAmount(UnitTestCase):
	def test_native_numbers_pass_straight_through(self):
		"""openpyxl hands back real floats; re-parsing them through str() would be lossy."""
		self.assertEqual(parse_amount(1234.56), 1234.56)
		self.assertEqual(parse_amount(-40), -40.0)
		self.assertEqual(parse_amount(0), 0.0)

	def test_booleans_are_not_numbers(self):
		"""bool is a subclass of int. Treating True as 1.0 would invent a one-rupee row."""
		self.assertIsNone(parse_amount(True))
		self.assertIsNone(parse_amount(False))

	def test_thousands_separators_and_currency_symbols_are_stripped(self):
		self.assertEqual(parse_amount("1,23,456.78"), 123456.78)
		self.assertEqual(parse_amount("₹ 999"), 999.0)
		self.assertEqual(parse_amount("INR 1,234.50"), 1234.50)

	def test_a_currency_prefix_ending_in_a_period_defeats_the_parser(self):
		"""Known limitation, pinned so a fix is a deliberate change rather than a surprise.

		The cleanup regex keeps `.` because decimals need it, so the period in "Rs."
		survives into the number and `float(".1234.50")` fails. No bank export seen so far
		writes the currency into the amount cell that way - the cell is either a native
		float or a bare number - so this is documented rather than worked around.
		"""
		self.assertIsNone(parse_amount("Rs. 1,234.50"))

	def test_dr_suffix_makes_the_amount_negative(self):
		self.assertEqual(parse_amount("1,234.56 Dr"), -1234.56)
		self.assertEqual(parse_amount("1,234.56 dr."), -1234.56)

	def test_cr_suffix_leaves_the_amount_positive(self):
		self.assertEqual(parse_amount("1,234.56 Cr"), 1234.56)
		self.assertEqual(parse_amount("500 CR"), 500.0)

	def test_accounting_parentheses_mean_negative(self):
		self.assertEqual(parse_amount("(1,234.56)"), -1234.56)

	def test_an_empty_cell_is_none_not_zero(self):
		"""A debit/credit pair leaves one column genuinely empty. Reading that as 0.0
		would make every row look like both a debit and a credit."""
		for blank in (None, "", "   ", "-", "--", "NA", "N/A", "nil", "Nil"):
			with self.subTest(blank=blank):
				self.assertIsNone(parse_amount(blank))

	def test_text_that_is_not_an_amount_is_none(self):
		self.assertIsNone(parse_amount("BALANCE"))
		self.assertIsNone(parse_amount("."))

	def test_zero_is_kept_as_zero(self):
		"""Distinct from None: a stated zero is a value, an empty column is not."""
		self.assertEqual(parse_amount("0.00"), 0.0)


class TestParseDate(UnitTestCase):
	def test_real_date_objects_pass_through(self):
		self.assertEqual(parse_date(datetime.date(2026, 4, 1)), datetime.date(2026, 4, 1))
		self.assertEqual(parse_date(datetime.datetime(2026, 4, 1, 13, 45)), datetime.date(2026, 4, 1))

	def test_dayfirst_is_the_default(self):
		"""Indian statements are dd/mm, and 05/03 is March 5th here, not May 3rd."""
		self.assertEqual(parse_date("05/03/2026"), datetime.date(2026, 3, 5))

	def test_dayfirst_can_be_turned_off(self):
		self.assertEqual(parse_date("05/03/2026", dayfirst=False), datetime.date(2026, 5, 3))

	def test_separators_are_interchangeable(self):
		for text in ("01/04/2026", "01-04-2026", "01.04.2026"):
			with self.subTest(text=text):
				self.assertEqual(parse_date(text), datetime.date(2026, 4, 1))

	def test_a_four_digit_leading_component_is_read_as_a_year(self):
		"""2026-04-01 is unambiguous whatever `dayfirst` says."""
		self.assertEqual(parse_date("2026-04-01"), datetime.date(2026, 4, 1))
		self.assertEqual(parse_date("2026-04-01", dayfirst=False), datetime.date(2026, 4, 1))

	def test_two_digit_years_pivot_at_seventy(self):
		self.assertEqual(parse_date("01/04/26"), datetime.date(2026, 4, 1))
		self.assertEqual(parse_date("01/04/69"), datetime.date(2069, 4, 1))
		self.assertEqual(parse_date("01/04/70"), datetime.date(1970, 4, 1))

	def test_a_trailing_time_component_is_ignored(self):
		self.assertEqual(parse_date("01/04/2026 13:45:00"), datetime.date(2026, 4, 1))

	def test_written_out_months_are_understood(self):
		self.assertEqual(parse_date("01 Apr 2026"), datetime.date(2026, 4, 1))
		self.assertEqual(parse_date("01-Apr-2026"), datetime.date(2026, 4, 1))
		self.assertEqual(parse_date("1 April 2026"), datetime.date(2026, 4, 1))
		self.assertEqual(parse_date("01-Apr-26"), datetime.date(2026, 4, 1))

	def test_a_cell_that_is_not_a_date_is_none(self):
		"""This is what tells a transaction row from a page header or a blank separator."""
		for value in (None, "", "   ", "Narration", "Opening Balance"):
			with self.subTest(value=value):
				self.assertIsNone(parse_date(value))

	def test_an_impossible_date_is_none_rather_than_a_crash(self):
		self.assertIsNone(parse_date("31/02/2026"))
		self.assertIsNone(parse_date("45/13/2026"))


class TestDetectDayfirst(UnitTestCase):
	def test_a_second_component_above_twelve_settles_the_column_as_month_first(self):
		self.assertFalse(detect_dayfirst(["03/15/2026", "04/02/2026"]))

	def test_a_first_component_above_twelve_settles_the_column_as_day_first(self):
		self.assertTrue(detect_dayfirst(["15/03/2026", "02/04/2026"]))

	def test_an_ambiguous_column_defaults_to_day_first(self):
		"""Every value here reads either way. Indian statements are dd/mm."""
		self.assertTrue(detect_dayfirst(["01/02/2026", "03/04/2026"]))

	def test_one_unambiguous_value_decides_the_whole_column(self):
		"""The reason this is a column-wide decision and not a per-cell one."""
		self.assertFalse(detect_dayfirst(["01/02/2026", "02/28/2026", "03/04/2026"]))

	def test_real_date_objects_are_skipped(self):
		"""openpyxl already resolved those; they say nothing about the string format."""
		self.assertTrue(detect_dayfirst([datetime.date(2026, 3, 15), "01/02/2026"]))

	def test_iso_dates_say_nothing_about_dayfirst(self):
		"""A leading year is not a high day, and must not be read as one."""
		self.assertTrue(detect_dayfirst(["2026-03-15", "2026-04-02"]))

	def test_an_empty_column_defaults_to_day_first(self):
		self.assertTrue(detect_dayfirst([]))
		self.assertTrue(detect_dayfirst([None, "", "Narration"]))
