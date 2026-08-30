import { expect, test } from '@playwright/test';
import { APP_BASE, E2E_USER, appUrl } from '../../helpers';

/**
 * The shell: does /wallet boot at all, and does the bottom tab bar go where it says.
 *
 * This is the tracer bullet for the whole PWA — it fails loudly when the Vite build is
 * missing (the build output is gitignored, so a fresh clone serves nothing), when the
 * `/wallet/<path>` route rule regresses, or when the router's basename drifts.
 */
test.describe('PWA shell', () => {
	test('boots at /wallet and lands on the dashboard', async ({ page }) => {
		await page.goto(APP_BASE);

		await expect(page.getByRole('heading', { name: 'Wallet' })).toBeVisible();
		await expect(page.getByText('Net worth')).toBeVisible();
	});

	test('the bottom tab bar navigates between screens', async ({ page }) => {
		await page.goto(APP_BASE);

		const nav = page.locator('nav');
		await expect(nav.getByRole('link', { name: 'Home' })).toBeVisible();

		await nav.getByRole('link', { name: 'Activity' }).click();
		await expect(page).toHaveURL(new RegExp(`${appUrl('transactions')}$`));
		await expect(page.getByRole('heading', { name: 'Activity' })).toBeVisible();

		await nav.getByRole('link', { name: 'More' }).click();
		await expect(page).toHaveURL(new RegExp(`${appUrl('settings')}$`));
		await expect(page.getByRole('heading', { name: 'More' })).toBeVisible();

		await nav.getByRole('link', { name: 'Home' }).click();
		await expect(page).toHaveURL(new RegExp(`${APP_BASE}/?$`));
		await expect(page.getByRole('heading', { name: 'Wallet' })).toBeVisible();
	});

	test('a deep link is served directly, not only reached by clicking', async ({
		page,
	}) => {
		// A hard navigation exercises the server-side route rule; clicking only ever
		// exercises the client router, so this catches a rewrite regression the tab-bar
		// test cannot see.
		await page.goto(appUrl('transactions'));

		await expect(page.getByRole('heading', { name: 'Activity' })).toBeVisible();
	});

	test('an unknown path falls back to the dashboard', async ({ page }) => {
		await page.goto(appUrl('does-not-exist'));

		await expect(page).toHaveURL(new RegExp(`${APP_BASE}/?$`));
		await expect(page.getByRole('heading', { name: 'Wallet' })).toBeVisible();
	});

	test('the session belongs to the seeded user, not Administrator', async ({
		page,
	}) => {
		await page.goto(appUrl('settings'));

		await expect(page.getByText('Signed in as')).toBeVisible();
		await expect(page.getByText(E2E_USER, { exact: true })).toBeVisible();
	});
});
