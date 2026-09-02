# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.api.permission`.

One function: the gate `hooks.add_to_apps_screen` calls to decide whether Wallet shows up
on the /apps screen and in the desk app switcher. It is a visibility gate, not a security
boundary - the data behind it is protected by `wallet/permissions.py` either way - so it
is deliberately generous: anyone who can keep their own transactions gets the tile.
"""

import frappe
from frappe.tests import IntegrationTestCase, set_user

from wallet.api.permission import has_app_permission
from wallet.tests.fixtures import commit, make_user


class TestHasAppPermission(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.holder = make_user("gate-holder@example.com")
		cls.manager = make_user("gate-manager@example.com", roles=("System Manager",))
		cls.outsider = make_user("gate-outsider@example.com", roles=())
		commit()

	def test_a_wallet_user_sees_the_app(self):
		with set_user(self.holder):
			self.assertTrue(has_app_permission())

	def test_a_system_manager_sees_the_app(self):
		"""Not because it is exempt from isolation - it is not, see permissions.py - but
		because it is the role a site administrator will be wearing when they go looking."""
		with set_user(self.manager):
			self.assertTrue(has_app_permission())

	def test_administrator_sees_the_app(self):
		with set_user("Administrator"):
			self.assertTrue(has_app_permission())

	def test_a_user_with_neither_role_does_not(self):
		with set_user(self.outsider):
			self.assertFalse(has_app_permission())

	def test_the_gate_is_wired_into_the_apps_screen_entry(self):
		"""The function can be perfectly correct and simply not be called."""
		from wallet import hooks

		self.assertEqual(
			hooks.add_to_apps_screen[0]["has_permission"],
			"wallet.api.permission.has_app_permission",
		)
