# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Decrypting password-protected statement workbooks.

Banks that email statements almost always encrypt them, with a password derived from
your date of birth, PAN or customer id. The result is not a zip archive at all: it is an
OLE2 compound document (ECMA-376 encryption) wrapping the real xlsx, and openpyxl
cannot open it. It has to be decrypted in memory first.
"""

import io

import frappe
from frappe import _

#: OLE2 compound document magic. An xlsx that begins with this is encrypted, because a
#: normal xlsx is a zip and begins with "PK".
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class StatementDecryptionError(frappe.ValidationError):
	"""Raised for a wrong or missing statement password."""


def is_encrypted(content: bytes) -> bool:
	return content[:8] == OLE2_MAGIC


def decrypt(content: bytes, password: str | None = None) -> bytes:
	"""Return decrypted workbook bytes, or the input unchanged if it is not encrypted."""
	if not is_encrypted(content):
		return content

	if not password:
		raise StatementDecryptionError(
			_("This statement is password protected. Enter the password your bank uses.")
		)

	try:
		import msoffcrypto
	except ImportError:
		frappe.throw(
			_(
				"msoffcrypto-tool is not installed. Run `bench setup requirements` to install "
				"the Wallet app's dependencies."
			)
		)

	source = io.BytesIO(content)
	target = io.BytesIO()

	try:
		office_file = msoffcrypto.OfficeFile(source)
		office_file.load_key(password=password)
		office_file.decrypt(target)
	except Exception as e:
		# Never surface the underlying traceback: it is noise to the user, and the only
		# actionable cause is almost always a wrong password.
		frappe.log_error(title="Wallet statement decryption failed", message=frappe.get_traceback())
		raise StatementDecryptionError(
			_("Could not open the statement. Check the password and try again.")
		) from e

	return target.getvalue()
