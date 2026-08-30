import { defineConfig, devices } from '@playwright/test';

// Auth state written by e2e/tests/auth.setup.ts (gitignored).
const authFile = 'e2e/.auth/user.json';

/**
 * Playwright configuration for the Wallet E2E suite.
 *
 * Authentication uses the "setup project" pattern: a setup project logs in once and
 * saves the session, and every other project reuses it.
 *
 * The suite deliberately never logs in as Administrator. `wallet/permissions.py` exempts
 * Administrator from owner isolation, so a browser holding that session would pass the
 * isolation specs no matter how broken the query conditions were. The user it does log
 * in as is created by `wallet/tests/e2e_seed.py`.
 *
 * @see https://playwright.dev/docs/auth
 */
export default defineConfig({
	testDir: './e2e/tests',
	// Sequential: the fixtures are shared server-side state, and Frappe's session
	// handling does not appreciate a fan-out of parallel writes against one site.
	fullyParallel: false,
	workers: 1,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'html',
	timeout: 60000,

	expect: {
		timeout: 10000,
	},

	use: {
		baseURL: process.env.BASE_URL || 'http://wallet.test:8000',
		// The browser and the site have to agree on what "today" is. Frappe derives
		// `nowdate()` from System Settings, which only the setup wizard ever fills in - a
		// site built by CI never runs it and falls through to `get_system_timezone()`'s
		// hard-coded "Asia/Kolkata", while the runner itself is UTC. Left alone, every
		// date the seeder writes is 5.5 hours out of step with the browser reading it, and
		// the "Today" grouping breaks outright between 18:30 and 00:00 UTC.
		//
		// Undefined means "use this machine's zone", which is right for a developer whose
		// laptop and site already agree. CI derives the value from the running site.
		// auth.setup.ts fails loudly if the two ever disagree.
		timezoneId: process.env.WALLET_E2E_TZ,
		trace: 'on-first-retry',
		video: 'retain-on-failure',
		screenshot: 'only-on-failure',
		actionTimeout: 15000,
		navigationTimeout: 30000,
	},

	projects: [
		{
			name: 'setup',
			testMatch: /auth\.setup\.ts/,
		},
		{
			// The PWA is mobile-first — a bottom tab bar with 56px touch targets. Pixel 7
			// keeps the run on chromium (no extra browser download) while giving the specs
			// touch and isMobile, so they exercise the layout users actually get.
			name: 'pwa',
			use: { ...devices['Pixel 7'], storageState: authFile },
			testMatch: /tests\/pwa\/.*\.spec\.ts$/,
			dependencies: ['setup'],
		},
		{
			// Desk forms and the REST API are desktop territory.
			name: 'desk',
			use: { ...devices['Desktop Chrome'], storageState: authFile },
			testMatch: /tests\/(desk|api)\/.*\.spec\.ts$/,
			dependencies: ['setup'],
		},
	],
});
