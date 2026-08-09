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
);
