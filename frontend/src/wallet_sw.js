/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { NetworkFirst } from "workbox-strategies";

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

// Read-only Wallet endpoints may be served stale when the network is down. Only GETs:
// caching a POST would silently swallow a write.
registerRoute(
	({ url, request }) =>
		request.method === "GET" && url.pathname.startsWith("/api/method/wallet."),
	new NetworkFirst({
		cacheName: "wallet-api",
		networkTimeoutSeconds: 5,
		plugins: [],
	})
);

self.addEventListener("message", (event) => {
	if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});
