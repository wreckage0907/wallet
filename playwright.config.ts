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
