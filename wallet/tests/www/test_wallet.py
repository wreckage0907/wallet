# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.www.wallet`.

The boot payload the PWA shell is rendered with. Small, but it is the first thing every
session touches, and two of its properties matter more than their size suggests: a Guest
must never get the shell, and the dev-only boot endpoint must stay dev-only - it is
`allow_guest=True`, so `developer_mode` is the only thing standing in front of it.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.tests.fixtures import commit, make_user
from wallet.www.wallet import get_boot, get_context, get_context_for_dev


class TestGetBoot(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("boot-holder@example.com")
		commit()

	def test_it_names_the_session_user(self):
		with set_user(self.user):
			boot = get_boot()

		self.assertEqual(boot["user"], self.user)

	def test_it_carries_the_display_name_the_ui_greets_you_with(self):
		with set_user(self.user):
			boot = get_boot()

		self.assertTrue(boot["user_full_name"])

	def test_it_carries_the_site_and_the_framework_version(self):
		boot = get_boot()

		self.assertEqual(boot["site_name"], frappe.local.site)
		self.assertEqual(boot["frappe_version"], frappe.__version__)

	def test_it_carries_a_timezone(self):
		"""Dates are written in site time and read back through the browser's clock, so
		the shell has to be told which zone the server means."""
		self.assertTrue(get_boot()["system_timezone"])

	def test_it_reports_read_only_mode(self):
		"""The UI has to stop offering to save things the site will refuse."""
		self.assertIn("read_only_mode", get_boot())


class TestGetContext(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("context-holder@example.com")
		commit()

	def test_a_guest_never_gets_the_shell(self):
		with set_user("Guest"), self.assertRaises(frappe.PermissionError):
			get_context()

	def test_a_holder_gets_a_boot_payload(self):
		with set_user(self.user):
			context = get_context()

		self.assertEqual(context.boot["user"], self.user)

	def test_the_boot_payload_carries_a_csrf_token(self):
		"""Every write the PWA makes is a POST, and without this the first one 403s."""
		with set_user(self.user):
			context = get_context()

		self.assertTrue(context.boot["csrf_token"])


class TestGetContextForDev(IntegrationTestCase):
	"""The `yarn dev` boot endpoint: under Vite the page never passes through the
	template, so the shell has to fetch its boot payload instead."""

	def test_it_is_refused_when_developer_mode_is_off(self):
		"""It is `allow_guest=True`, so this check is the only thing in front of it."""
		previous = frappe.conf.developer_mode
		frappe.conf.developer_mode = 0
		try:
			with self.assertRaises(frappe.ValidationError):
				get_context_for_dev()
		finally:
			frappe.conf.developer_mode = previous

	def test_it_returns_the_boot_payload_in_developer_mode(self):
		previous = frappe.conf.developer_mode
		frappe.conf.developer_mode = 1
		try:
			boot = get_context_for_dev()
		finally:
			frappe.conf.developer_mode = previous

		self.assertEqual(boot["user"], frappe.session.user)
