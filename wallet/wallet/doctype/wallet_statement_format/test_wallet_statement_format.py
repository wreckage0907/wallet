# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for the Wallet Statement Format controller.

A remembered column mapping for one bank's export. Shared rather than owner-isolated,
deliberately: a mapping holds no personal data, and sharing means the second person to
import an HDFC statement gets it for free.

Validation is the whole controller, and it is worth having because a format is used
*instead of* the detection heuristic. A format missing a date column does not fall back to
guessing - it takes the import straight to "the column mapping needs a date column", on
every statement from that bank, until someone fixes the format.
"""

import frappe
from frappe.tests import IntegrationTestCase

from wallet.tests.fixtures import commit, make_bank, make_user, purge


def make_format(targets: dict[str, int], amount_convention: str, format_name: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Wallet Statement Format",
				"format_name": format_name,
				"bank": make_bank(),
				"file_type": "XLSX",
				"amount_convention": amount_convention,
				"mappings": [
					{"target_field": target, "column_index": index} for target, index in targets.items()
				],
			}
		)
		.insert()
		.name
	)


class TestWalletStatementFormat(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("fmt-holder@example.com")
		purge(cls.user)
		frappe.db.delete("Wallet Statement Format", {"format_name": ["like", "Fmt %"]})
		commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("Wallet Statement Format", {"format_name": ["like", "Fmt %"]})
		purge(cls.user)
		commit()
		super().tearDownClass()

	# --- validation -------------------------------------------------------------------

	def test_a_mapping_with_no_date_column_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_format({"debit": 4, "credit": 5}, "Separate Debit/Credit Columns", "Fmt No Date")

	def test_either_date_column_satisfies_the_requirement(self):
		"""Some exports carry only a value date, and that is a usable posting date."""
		for date_field in ("posting_date", "value_date"):
			with self.subTest(date_field=date_field):
				name = make_format(
					{date_field: 0, "debit": 4, "credit": 5},
					"Separate Debit/Credit Columns",
					f"Fmt {date_field}",
				)

				self.assertTrue(frappe.db.exists("Wallet Statement Format", name))

	def test_the_debit_credit_convention_needs_one_of_those_columns(self):
		with self.assertRaises(frappe.ValidationError):
			make_format({"posting_date": 0, "amount": 3}, "Separate Debit/Credit Columns", "Fmt Mismatch")

	def test_a_debit_column_alone_satisfies_the_debit_credit_convention(self):
		"""Credit-card statements often have only a spend column."""
		name = make_format({"posting_date": 0, "debit": 4}, "Separate Debit/Credit Columns", "Fmt Debit Only")

		self.assertTrue(frappe.db.exists("Wallet Statement Format", name))

	def test_the_single_amount_conventions_need_an_amount_column(self):
		for convention in ("Single Signed Amount", "Amount + Dr/Cr Indicator"):
			with self.subTest(convention=convention), self.assertRaises(frappe.ValidationError):
				make_format({"posting_date": 0, "debit": 4}, convention, f"Fmt {convention}")

	def test_a_complete_mapping_saves(self):
		name = make_format(
			{"posting_date": 0, "description": 1, "amount": 3, "balance_after": 6},
			"Single Signed Amount",
			"Fmt Complete",
		)

		self.assertTrue(frappe.db.exists("Wallet Statement Format", name))

	# --- get_mapping ------------------------------------------------------------------

	def test_get_mapping_keys_by_target_field(self):
		"""It is consumed as `target -> column index` by the import pipeline, which never
		sees the child table."""
		name = make_format(
			{"posting_date": 0, "description": 1, "amount": 3}, "Single Signed Amount", "Fmt Mapping"
		)

		mapping = frappe.get_doc("Wallet Statement Format", name).get_mapping()

		self.assertEqual(mapping["posting_date"]["index"], 0)
		self.assertEqual(mapping["description"]["index"], 1)
		self.assertEqual(mapping["amount"]["index"], 3)

	def test_get_mapping_carries_the_label_and_transform(self):
		doc = frappe.get_doc(
			{
				"doctype": "Wallet Statement Format",
				"format_name": "Fmt Transform",
				"bank": make_bank(),
				"file_type": "XLSX",
				"amount_convention": "Single Signed Amount",
				"mappings": [
					{"target_field": "posting_date", "column_index": 0, "column_label": "Txn Date"},
					{"target_field": "amount", "column_index": 3, "transform": "Absolute"},
				],
			}
		).insert()

		mapping = doc.get_mapping()

		self.assertEqual(mapping["posting_date"]["label"], "Txn Date")
		self.assertEqual(mapping["amount"]["transform"], "Absolute")

	def test_a_format_is_visible_to_every_holder(self):
		"""Not owner-isolated, deliberately - it holds no personal data, and sharing it is
		what makes the second HDFC import free."""
		name = make_format({"posting_date": 0, "amount": 3}, "Single Signed Amount", "Fmt Shared")
		commit()

		from frappe.tests import set_user

		with set_user(self.user):
			self.assertTrue(frappe.get_list("Wallet Statement Format", filters={"name": name}))
