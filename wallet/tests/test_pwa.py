# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.pwa`.

A service worker can only control URLs at or below the directory it is served from, so a
worker under `/assets/wallet/frontend/` can never control `/wallet` - no offline shell,
and no install prompt, because Chrome requires a worker that controls `start_url`. Frappe's
own static server refuses to serve `js` and `json`, so `www/` is not an option either.
Hence a `page_renderer`, serving the worker from the site root.

Three things have to hold for that to work, and each is easy to break without noticing
because the failure is silent in the browser console rather than on the server: the path
has to be claimed, the MIME type has to be `application/javascript`, and the response must
not be cacheable.

The build output is gitignored, so `wallet/public/frontend/wallet_sw.js` exists only after
`yarn build`. Tests that need the real file skip without it rather than fail - CI runs a
build, a fresh clone may not have.
"""

import unittest
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from wallet.pwa import ROOT_FILES, PWAAssetRenderer


def worker_path() -> Path:
	return Path(frappe.get_app_path("wallet", "public", "frontend")) / "wallet_sw.js"


class TestPWAAssetRenderer(IntegrationTestCase):
	def renderer(self, path: str) -> PWAAssetRenderer:
		return PWAAssetRenderer(path)

	def test_it_only_claims_the_paths_it_knows(self):
		"""`can_render` is consulted for every request that reaches the renderer chain, so
		claiming anything else would take pages away from the rest of the site."""
		# An empty path is deliberately absent: `BaseRenderer` falls back to
		# `frappe.request.path` for a falsy one, which does not exist outside a request.
		for path in ("wallet", "app/wallet", "assets/wallet/frontend/index.html", "wallet_sw.js.map"):
			with self.subTest(path=path):
				self.assertFalse(self.renderer(path).can_render())

	def test_the_worker_filename_has_no_slash_in_it(self):
		"""`website_route_rules` maps `/wallet/<path>` to the app, so a worker at
		`/wallet/sw.js` would be swallowed by it and never served."""
		for path in ROOT_FILES:
			with self.subTest(path=path):
				self.assertNotIn("/", path)

	@unittest.skipUnless(worker_path().is_file(), "PWA build output is gitignored; run `yarn build`")
	def test_it_claims_the_worker_path(self):
		self.assertTrue(self.renderer("wallet_sw.js").can_render())

	@unittest.skipUnless(worker_path().is_file(), "PWA build output is gitignored; run `yarn build`")
	def test_the_worker_is_served_as_javascript(self):
		"""A wrong MIME type makes the browser refuse to register the worker at all, and
		`mimetypes.guess_type` is free to return `text/javascript`."""
		renderer = self.renderer("wallet_sw.js")
		renderer.render()

		self.assertEqual(renderer.headers["Content-Type"], "application/javascript")

	@unittest.skipUnless(worker_path().is_file(), "PWA build output is gitignored; run `yarn build`")
	def test_the_worker_is_never_cached(self):
		"""A cached worker leaves users stuck on an old shell with no way to move them."""
		renderer = self.renderer("wallet_sw.js")
		renderer.render()

		cache_control = renderer.headers["Cache-Control"]
		self.assertIn("no-store", cache_control)
		self.assertIn("must-revalidate", cache_control)

	@unittest.skipUnless(worker_path().is_file(), "PWA build output is gitignored; run `yarn build`")
	def test_the_worker_body_is_the_file_on_disk(self):
		response = self.renderer("wallet_sw.js").render()

		self.assertEqual(response.get_data(), worker_path().read_bytes())

	def test_a_missing_build_is_not_claimed(self):
		"""`can_render` checks the file exists, so a bench that has never run `yarn build`
		404s rather than 500s."""
		renderer = self.renderer("wallet_sw.js")

		self.assertEqual(renderer.can_render(), worker_path().is_file())

	def test_the_renderer_is_registered(self):
		from wallet import hooks

		self.assertIn("wallet.pwa.PWAAssetRenderer", hooks.page_renderer)
