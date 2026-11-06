import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { FrappeProvider } from "frappe-react-sdk";

import App from "./App.jsx";
import "./index.css";

// The worker is served from the site root so it can claim scope "/wallet"; a worker
// under /assets/ could only ever control /assets/. See wallet/pwa.py.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
	const register = () =>
		navigator.serviceWorker
			.register("/wallet_sw.js", { scope: "/wallet" })
			.catch((error) => console.warn("Wallet service worker registration failed", error));

	// A bare load listener is not enough: this is a deferred module script, and by the
	// time it runs the load event has often already fired, so the listener would never
	// be called and the worker would silently never register.
	if (document.readyState === "complete") register();
	else window.addEventListener("load", register, { once: true });
}

// Under `yarn dev` Vite serves index.html as-is, so window.csrf_token is still the
// unrendered "{{ frappe.session.csrf_token }}". frappe-react-sdk only recognises the
// literal "{{ csrf_token }}" as a placeholder, so it would send that text as the token
// and every POST would fail with "Invalid Request". Fetch the session's real token from
// the dev boot endpoint instead (over GET, which Frappe does not CSRF-check).
async function loadDevCsrfToken() {
	window.csrf_token = undefined;
	try {
		const response = await fetch("/api/method/wallet.www.wallet.get_context_for_dev", {
			credentials: "include",
		});
		const { message } = await response.json();
		if (message?.csrf_token) window.csrf_token = message.csrf_token;
	} catch (error) {
		console.warn("Could not fetch a CSRF token for the dev server", error);
	}
}

const ready = import.meta.env.DEV ? loadDevCsrfToken() : Promise.resolve();

ready.then(() =>
	createRoot(document.getElementById("root")).render(
		<StrictMode>
			<FrappeProvider
				socketPort={import.meta.env.VITE_SOCKET_PORT}
				swrConfig={{ revalidateOnFocus: false, shouldRetryOnError: false }}
			>
				<BrowserRouter basename="/wallet">
					<App />
				</BrowserRouter>
			</FrappeProvider>
		</StrictMode>
	)
);
