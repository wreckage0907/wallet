# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WalletStatementFormat(Document):
	"""A remembered column mapping for one bank's statement export.

	Shared, not owner-isolated: a column mapping contains no personal data, and sharing
	means the second person to import an HDFC statement gets the mapping for free.
	"""

	def validate(self) -> None:
		self.validate_mapping_completeness()

	def validate_mapping_completeness(self) -> None:
		targets = {row.target_field for row in self.mappings}

		if not ({"posting_date", "value_date"} & targets):
			frappe.throw(_("The mapping needs a date column."))

		if self.amount_convention == "Separate Debit/Credit Columns":
			if not ({"debit", "credit"} & targets):
				frappe.throw(_("This convention needs a debit or credit column."))
		elif "amount" not in targets:
			frappe.throw(_("This convention needs an amount column."))

	def get_mapping(self) -> dict:
		"""target field -> {"label": ..., "index": ..., "transform": ...}"""
		return {
			row.target_field: {
				"label": row.column_label,
				"index": row.column_index,
				"transform": row.transform,
			}
			for row in self.mappings
		}
