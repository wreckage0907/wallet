import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

// The bench's port lives in sites/common_site_config.json, three directories up - a file
// that only exists when this app is checked out inside a bench. A bare clone has no
// bench, and vite.config.js imports this module at load time, so a static
// `require("../../../sites/common_site_config.json")` here fails to *resolve* at bundle
// time and takes `yarn build` down with it - even though the proxy is only ever used by
// `yarn dev`. Reading the file at runtime keeps the path out of the bundler's hands.
function webserverPort(fallback = 8000) {
	try {
		const config = resolve(here, "../../../sites/common_site_config.json");
		return JSON.parse(readFileSync(config, "utf-8")).webserver_port ?? fallback;
	} catch {
		// No bench around: this is a build, or a dev server with nothing to proxy to.
		return fallback;
	}
}

const webserver_port = webserverPort();

export default {
	'^/(app|api|assets|files|private)': {
		target: `http://127.0.0.1:${webserver_port}`,
		ws: true,
		router: function(req) {
			const site_name = req.headers.host.split(':')[0];
			return `http://${site_name}:${webserver_port}`;
		}
	}
};
