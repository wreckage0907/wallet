# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WalletBank(Document):
	"""Shared reference data - a bank, not an account.

	Deliberately NOT owner-isolated: it holds no personal data, and sharing it means a
	Wallet Statement Format saved by one user is reusable by every other user of the
	same bank. See wallet/permissions.py for the doctypes that *are* isolated.
	"""

	pass
