# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Serving the service worker from the site root.

A service worker can only control URLs at or below the directory it is served from.
The built assets live at `/assets/wallet/frontend/`, so a worker served from there is
confined to that prefix and can never control `/wallet` - no offline shell, and no
install prompt, because Chrome requires a worker that controls `start_url`.

Frappe's own static file server is not an option either: `StaticPage` explicitly refuses
to serve `js` and `json` (frappe/website/page_renderers/static_page.py,
UNSUPPORTED_STATIC_PAGE_TYPES), so dropping the worker into `www/` gets a 404.

So the worker is served from the site root through the supported `page_renderer` hook,
with the correct MIME type. Being at the root, it may legally claim scope `/wallet` with
no `Service-Worker-Allowed` header.

The manifest needs none of this: its `scope` and `start_url` are absolute, so they
resolve against the origin no matter where the manifest itself is served from. It stays
under /assets/ where vite-plugin-pwa emits it, and the plugin injects its own <link>.

Note the filename deliberately has no slash after "wallet": `website_route_rules` maps
`/wallet/<path>` to the app, and a path like `/wallet/sw.js` would be swallowed by it.
"""

import mimetypes
from pathlib import Path

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer

#: request path -> file inside wallet/public/frontend/
ROOT_FILES = {
	"wallet_sw.js": "wallet_sw.js",
}


class PWAAssetRenderer(BaseRenderer):
	"""Serves the Wallet service worker from the site root."""

	def can_render(self) -> bool:
		return self.path in ROOT_FILES and self._file_path().is_file()

	def _file_path(self) -> Path:
		return Path(frappe.get_app_path("wallet", "public", "frontend")) / ROOT_FILES.get(self.path, "")

	def render(self):
		path = self._file_path()
		content = path.read_bytes()

		content_type = mimetypes.guess_type(path.name)[0]
		if path.suffix == ".js":
			# guess_type can return text/javascript; be explicit, since a wrong MIME type
			# makes the browser refuse to register the worker at all.
			content_type = "application/javascript"

		self.headers = {
			"Content-Type": content_type or "application/octet-stream",
			# The worker must never be cached, or users get stuck on an old shell.
			"Cache-Control": "no-cache, no-store, must-revalidate",
		}

		return self.build_response(content)
