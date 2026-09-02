# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.settings`.

The whole module exists for one framework behaviour: a Single that has never been saved
has no row in `tabSingles`, and `frappe.db.get_single_value` casts that missing value
through the field's type - so a Check comes back as `0`, never `None`. Read
`auto_categorize` directly on a fresh site and it reports "disabled" even though the field
is declared with a default of 1, and auto-categorization silently never runs.

So the test that matters is the one with *no* stored row, which means deleting the row and
putting it back. Frappe rolls each test back, but these tests commit nothing and restore
explicitly anyway - the suite runs against a real dev site.
"""

import frappe
from frappe.tests import IntegrationTestCase

from wallet.settings import SETTINGS_DOCTYPE, get_setting


class TestGetSetting(IntegrationTestCase):
	def stored(self, fieldname: str):
		return frappe.db.get_value(
			"Singles", {"doctype": SETTINGS_DOCTYPE, "field": fieldname}, "value", order_by=None
		)

	def without_stored_value(self, fieldname: str):
		"""Delete the Singles row for one field and hand back a restore callable."""
		previous = self.stored(fieldname)
		frappe.db.delete("Singles", {"doctype": SETTINGS_DOCTYPE, "field": fieldname})

		def restore():
			frappe.db.delete("Singles", {"doctype": SETTINGS_DOCTYPE, "field": fieldname})
			if previous is not None:
				frappe.db.sql(
					"INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)",
					(SETTINGS_DOCTYPE, fieldname, previous),
				)

		return restore

	def test_an_unsaved_check_falls_back_to_its_declared_default(self):
		"""The bug this module was written for. `get_single_value` would say 0 here, and
		auto-categorization would never run on a site nobody had opened Settings on."""
		declared = frappe.get_meta(SETTINGS_DOCTYPE).get_field("auto_categorize").default
		self.assertEqual(str(declared), "1")

		restore = self.without_stored_value("auto_categorize")
		try:
			self.assertEqual(get_setting("auto_categorize"), 1)
		finally:
			restore()

	def test_the_default_is_cast_to_the_fields_type(self):
		"""DocField.default is text. An Int handed back as "5000" would break the row-limit
		comparison it feeds, which is a `>` against a length."""
		restore = self.without_stored_value("max_import_rows")
		try:
			value = get_setting("max_import_rows")
		finally:
			restore()

		self.assertIsInstance(value, int)

	def test_a_stored_value_wins_over_the_default(self):
		restore = self.without_stored_value("auto_categorize")
		try:
			frappe.db.sql(
				"INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)",
				(SETTINGS_DOCTYPE, "auto_categorize", "0"),
			)
			frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

			self.assertEqual(get_setting("auto_categorize"), 0)
		finally:
			restore()
			frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

	def test_a_stored_zero_is_not_mistaken_for_a_missing_row(self):
		"""`0` is falsy and `""` is the framework's empty. The lookup has to test against
		None, or turning a Check *off* would silently read back as its default of on."""
		restore = self.without_stored_value("auto_categorize")
		try:
			frappe.db.sql(
				"INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)",
				(SETTINGS_DOCTYPE, "auto_categorize", "0"),
			)
			frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

			self.assertFalse(get_setting("auto_categorize"))
		finally:
			restore()
			frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

	def test_an_unknown_field_throws_rather_than_returning_none(self):
		"""A typo'd fieldname returning None would read as "the feature is off"."""
		with self.assertRaises(frappe.ValidationError):
			get_setting("no_such_field")
