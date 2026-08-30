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
