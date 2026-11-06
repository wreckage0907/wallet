/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";

// Where the build output is served. Matches `--base` in package.json's build script.
const BASE = "/assets/wallet/frontend/";

// Precache the built shell. self.__WB_MANIFEST is replaced at build time.
//
// Its entries are relative to the build directory ("index.html", "assets/index-x.js"),
// and Workbox resolves a relative entry against the worker's own URL. This worker is
// served from the site root (see wallet/pwa.py), so "index.html" would become /index.html
// and 404, and one failed precache request fails the whole install. Anchor every entry
// here rather than with `modifyURLPrefix` in vite.config.js: vite-plugin-pwa appends the
// web manifest after Workbox's URL transforms run, so that option never reaches it.
const anchor = (url) => (url.startsWith("/") ? url : BASE + url);
precacheAndRoute(
	self.__WB_MANIFEST.map((entry) =>
		typeof entry === "string" ? anchor(entry) : { ...entry, url: anchor(entry.url) }
	)
);
cleanupOutdatedCaches();

// Navigations to /wallet/* fall back to the app shell so deep links work offline.
// Everything Frappe owns is excluded - serving a cached shell for /api or /app would
// break the desk and swallow API errors.
const shell = BASE + "index.html";
registerRoute(
	new NavigationRoute(
		async ({ event }) => {
			try {
				return await fetch(event.request);
			} catch {
				const cached = await caches.match(shell, { ignoreSearch: true });
				return cached || Response.error();
			}
		},
		{
			allowlist: [/^\/wallet(\/|$)/],
			denylist: [/^\/api/, /^\/app/, /^\/files/, /^\/private/, /^\/assets\/frappe/],
		}
	)
);

// API responses are deliberately NOT cached.
//
// Cache Storage is scoped to the origin, not to the session: it survives logout and is
// shared by whoever uses the browser next. Caching balances and transactions would mean
// a second user on the same device could be served the first user's financial data from
// cache the moment the network hiccuped. Offline support here would need per-user cache
// names purged on authentication change, which is not worth the risk for read-only data
// that is meaningless when stale.

self.addEventListener("message", (event) => {
	if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});
