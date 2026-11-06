# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Decrypting password-protected statement workbooks.

Banks that email statements almost always encrypt them, with a password derived from
your date of birth, PAN or customer id. The result is not a zip archive at all: it is an
OLE2 compound document (ECMA-376 encryption) wrapping the real xlsx, and openpyxl
cannot open it. It has to be decrypted in memory first.

Starting with the OLE2 magic is not enough to call a file encrypted, though: every
legacy Excel 97-2003 `.xls` is an OLE2 document too, encrypted or not. So the container
is opened and its streams decide:

* an `EncryptionInfo` stream is an ECMA-376 encrypted xlsx;
* a `Workbook` (or BIFF5 `Book`) stream is a legacy `.xls`, encrypted only when its
  workbook globals carry a FILEPASS record;
* anything else that starts with the magic is treated as encrypted, as before, so the
  user is asked for a password rather than shown a parser error.
"""

import io
import struct

import frappe
from frappe import _

#: OLE2 compound document magic. An xlsx that begins with this is encrypted, because a
#: normal xlsx is a zip and begins with "PK". A legacy `.xls` begins with it either way.
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

#: BIFF record types. FILEPASS marks an encrypted workbook; EOF ends the globals substream.
_BIFF_FILEPASS = 0x002F
_BIFF_EOF = 0x000A


class StatementDecryptionError(frappe.ValidationError):
	"""Raised for a wrong or missing statement password."""


def is_encrypted(content: bytes) -> bool:
	if content[:8] != OLE2_MAGIC:
		return False

	try:
		import olefile

		with olefile.OleFileIO(io.BytesIO(content)) as ole:
			if ole.exists("EncryptionInfo"):
				return True
			for stream in ("Workbook", "Book"):
				if ole.exists(stream):
					return _has_filepass(ole.openstream(stream).read())
	except Exception:
		# Not a container we can open. Fall through to the cautious answer.
		pass

	return True


def _has_filepass(workbook_stream: bytes) -> bool:
	"""Walk the BIFF records of the workbook globals, up to their EOF, for FILEPASS."""
	offset = 0
	while offset + 4 <= len(workbook_stream):
		record, size = struct.unpack_from("<HH", workbook_stream, offset)
		if record == _BIFF_FILEPASS:
			return True
		if record == _BIFF_EOF:
			return False
		offset += 4 + size

	return False


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
