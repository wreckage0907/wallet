# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.statement.decrypt`.

An encrypted xlsx is not a zip at all: it is an OLE2 compound document wrapping the real
workbook, so it begins with the OLE2 magic rather than "PK" and openpyxl cannot open it.
That single fact is what the module keys on, and it is what these tests pin.

There is no test that decrypts a real protected workbook, deliberately. `msoffcrypto-tool`
decrypts but does not encrypt, so a genuine fixture would have to be a checked-in file -
and a checked-in encrypted bank statement is exactly what the repo convention forbids.
What is testable without one is the routing and both failure paths, which is where the
behaviour a user actually meets lives.
"""

import frappe
from frappe.tests import IntegrationTestCase

from wallet.statement.decrypt import OLE2_MAGIC, StatementDecryptionError, decrypt, is_encrypted
from wallet.tests.fixtures import xlsx_bytes


class TestIsEncrypted(IntegrationTestCase):
	def test_an_ole2_document_is_encrypted(self):
		self.assertTrue(is_encrypted(OLE2_MAGIC + b"anything at all"))

	def test_a_plain_workbook_is_not(self):
		"""A normal xlsx is a zip and begins with "PK"."""
		content = xlsx_bytes([["Date", "Narration"]])

		self.assertEqual(content[:2], b"PK")
		self.assertFalse(is_encrypted(content))

	def test_a_csv_is_not(self):
		self.assertFalse(is_encrypted(b"Date,Narration\n"))

	def test_an_empty_file_is_not(self):
		"""Slicing past the end is fine in Python; this pins that it stays fine."""
		self.assertFalse(is_encrypted(b""))


class TestDecrypt(IntegrationTestCase):
	def test_an_unencrypted_file_passes_through_untouched(self):
		"""Every import goes through here, so the common case has to be a no-op - the same
		bytes back, not a re-encoded copy."""
		content = xlsx_bytes([["Date", "Narration"]])

		self.assertIs(decrypt(content), content)

	def test_a_password_on_an_unencrypted_file_is_ignored(self):
		content = xlsx_bytes([["Date", "Narration"]])

		self.assertIs(decrypt(content, password="irrelevant"), content)

	def test_an_encrypted_file_with_no_password_asks_for_one(self):
		"""The message has to name the bank's password, because that is the one thing the
		user has and the app does not."""
		with self.assertRaises(StatementDecryptionError) as caught:
			decrypt(OLE2_MAGIC + b"encrypted payload")

		self.assertIn("password", str(caught.exception).casefold())

	def test_an_empty_password_counts_as_no_password(self):
		for password in ("", None):
			with self.subTest(password=password), self.assertRaises(StatementDecryptionError):
				decrypt(OLE2_MAGIC + b"encrypted payload", password=password)

	def test_a_password_that_does_not_work_reports_that_and_nothing_else(self):
		"""The underlying traceback is noise to the user and the only actionable cause is
		almost always a wrong password. It goes to the error log instead."""
		with self.assertRaises(StatementDecryptionError) as caught:
			decrypt(OLE2_MAGIC + b"not actually a valid office file", password="wrong")

		message = str(caught.exception)
		self.assertIn("password", message.casefold())
		self.assertNotIn("Traceback", message)

	def test_the_failure_is_a_validation_error_the_api_layer_can_surface(self):
		"""It subclasses `frappe.ValidationError`, so the wizard reports it to the user
		rather than turning it into a 500."""
		self.assertTrue(issubclass(StatementDecryptionError, frappe.ValidationError))
