import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import proxyOptions from "./proxyOptions";

// The built assets are served from /assets/wallet/frontend/, but the app itself lives
// at /wallet. A service worker only controls URLs at or below its own directory, so the
// worker and manifest are emitted with root-ish names and served from the site root by
// wallet/pwa.py. See that module for why they cannot simply live in www/.
export default defineConfig({
	plugins: [
		react(),
		tailwindcss(),
		VitePWA({
			strategies: "injectManifest",
			srcDir: "src",
			filename: "wallet_sw.js",
			injectRegister: false, // registered by hand in main.jsx, with an explicit scope
			manifestFilename: "wallet_manifest.json",
			injectManifest: {
				globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
			},
			manifest: {
				name: "Wallet",
				short_name: "Wallet",
				description: "Track spending across all your bank accounts in one place",
				start_url: "/wallet",
				scope: "/wallet",
				display: "standalone",
				orientation: "portrait",
				background_color: "#0f172a",
				theme_color: "#0f172a",
				icons: [
					{ src: "/assets/wallet/frontend/icon-192.png", sizes: "192x192", type: "image/png" },
					{ src: "/assets/wallet/frontend/icon-512.png", sizes: "512x512", type: "image/png" },
					{
						src: "/assets/wallet/frontend/icon-512.png",
						sizes: "512x512",
						type: "image/png",
						purpose: "maskable",
					},
				],
			},
			devOptions: { enabled: false },
		}),
	],
	server: {
		port: 8080,
		host: "0.0.0.0",
		proxy: proxyOptions,
	},
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	build: {
		outDir: "../wallet/public/frontend",
		emptyOutDir: true,
		target: "es2020",
		sourcemap: false,
	},
});
