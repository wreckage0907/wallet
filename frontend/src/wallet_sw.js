/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";

// Precache the built shell. self.__WB_MANIFEST is replaced at build time.
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Navigations to /wallet/* fall back to the app shell so deep links work offline.
// Everything Frappe owns is excluded - serving a cached shell for /api or /app would
// break the desk and swallow API errors.
const shell = "/assets/wallet/frontend/index.html";
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
