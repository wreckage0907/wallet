# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Reading Wallet Settings safely.

`frappe.db.get_single_value` reads the `tabSingles` table, and a Single that has never
been opened and saved has no row there. The missing value is then cast through the
field's type - so a Check comes back as `0` and an Int as `0`, never as `None`. Reading
`auto_categorize` directly on a fresh site therefore reports "disabled" even though the
field is declared with a default of 1.

`get_setting` falls back to the DocField's declared default, so an untouched site
behaves exactly as the field definitions say it should.
"""

import frappe

SETTINGS_DOCTYPE = "Wallet Settings"


def get_setting(fieldname: str):
	"""Value of one Wallet Settings field, falling back to its declared default."""
	# order_by=None because tabSingles has no `creation` column to sort on.
	stored = frappe.db.get_value(
		"Singles", {"doctype": SETTINGS_DOCTYPE, "field": fieldname}, "value", order_by=None
	)
	if stored is not None:
		return frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)

	df = frappe.get_meta(SETTINGS_DOCTYPE).get_field(fieldname)
	if not df:
		frappe.throw(frappe._("Unknown Wallet Settings field: {0}").format(fieldname))

	return frappe.utils.cast(df.fieldtype, df.default)
