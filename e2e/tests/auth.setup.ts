import * as fs from 'node:fs';
import * as path from 'node:path';
import { expect, test as setup } from '@playwright/test';
import { E2E_PASSWORD, E2E_USER } from '../helpers';

const authFile = 'e2e/.auth/user.json';
const csrfFile = 'e2e/.auth/csrf.json';

/**
 * Runs once, before everything else.
 *
 * The user it logs in as is seeded by `wallet/tests/e2e_seed.py`. If this step fails
 * with "Incorrect password", the seed has not been run against this site:
 *
 *     bench --site wallet.test execute wallet.tests.e2e_seed.seed
 */
setup('authenticate', async ({ page }) => {
	fs.mkdirSync(path.dirname(authFile), { recursive: true });

	const loginResponse = await page.request.post('/api/method/login', {
		form: { usr: E2E_USER, pwd: E2E_PASSWORD },
	});
	expect(
		loginResponse.ok(),
		`Login failed for ${E2E_USER} — has wallet.tests.e2e_seed.seed been run?`,
	).toBeTruthy();

	const userResponse = await page.request.get(
		'/api/method/frappe.auth.get_logged_user',
	);
	expect(userResponse.ok()).toBeTruthy();
	const { message: user } = await userResponse.json();

	// The whole suite is meaningless as Administrator: permissions.py exempts it from
	// owner isolation, so every isolation assertion would pass vacuously.
	expect(user).toBe(E2E_USER);
	expect(user).not.toBe('Administrator');

	// The browser and the site must sit at the same UTC offset, or every date-shaped
	// assertion in the suite is a coin flip: the seeder writes `nowdate()` in site time
	// and the specs read it back through the browser's clock.
	//
	// Compared by offset, not by zone name - Chromium reports some zones under an alias
	// ("Asia/Calcutta" for "Asia/Kolkata"), which would be a false alarm. Comparing
	// today's *date* instead would be worse: it only diverges inside the very window the
	// mismatch breaks things, so a developer would see this pass all afternoon and fail
	// at 19:00 UTC with no idea why.
	const { message: zone } = await (
		await page.request.get('/api/method/frappe.client.get_time_zone')
	).json();
	const siteOffset = utcOffsetMinutes(zone.time_zone);
	const browserOffset = await page.evaluate(() => new Date().getTimezoneOffset());

	expect(
		browserOffset,
		`The browser is at UTC${offsetLabel(browserOffset)} but the site is on ` +
			`${zone.time_zone} (UTC${offsetLabel(siteOffset)}). ` +
			`Re-run with WALLET_E2E_TZ=${zone.time_zone}.`,
	).toBe(siteOffset);

	// The CSRF token only exists in the desk bootstrap; POST helpers read it from here.
	await page.goto('/app');
	await page.waitForLoadState('networkidle');

	const csrfToken = await page.evaluate(
		() =>
			(window as unknown as { frappe?: { csrf_token?: string } }).frappe
				?.csrf_token,
	);
	if (csrfToken) {
		fs.writeFileSync(csrfFile, JSON.stringify({ csrf_token: csrfToken }));
	}

	await page.context().storageState({ path: authFile });
});

/**
 * Minutes a zone sits behind UTC, in `Date.getTimezoneOffset()`'s sign convention
 * (positive west of Greenwich), so the two are directly comparable.
 */
function utcOffsetMinutes(zone: string, at = new Date()): number {
	const inZone = new Date(at.toLocaleString('en-US', { timeZone: zone }));
	const inUtc = new Date(at.toLocaleString('en-US', { timeZone: 'UTC' }));
	return Math.round((inUtc.getTime() - inZone.getTime()) / 60000);
}

/** "+05:30" / "-08:00", for an error message a human can act on. */
function offsetLabel(minutes: number): string {
	const ahead = -minutes;
	const sign = ahead < 0 ? '-' : '+';
	const abs = Math.abs(ahead);
	return `${sign}${String(Math.floor(abs / 60)).padStart(2, '0')}:${String(abs % 60).padStart(2, '0')}`;
}
