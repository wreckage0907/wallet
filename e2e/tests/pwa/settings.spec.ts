import { expect, test } from '@playwright/test';
import { E2E_USER, appUrl } from '../../helpers';

test.describe('More', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto(appUrl('settings'));
		await expect(page.getByRole('heading', { name: 'More' })).toBeVisible();
	});

	test('names the signed-in user', async ({ page }) => {
		await expect(page.getByText(E2E_USER, { exact: true })).toBeVisible();
	});

	test('recalculating balances reports how many it touched', async ({
		page,
	}) => {
		await page.getByRole('button', { name: 'Recalculate balances' }).click();

		// Two seeded accounts, and the repair path for a stale `cached_balance` is the only
		// thing standing between the account list and a wrong number.
		await expect(page.getByText(/Rebuilt 2 account balances\./)).toBeVisible();
	});

	test('restoring defaults is a no-op when nothing is missing', async ({
		page,
	}) => {
		// The seed installs the full default tree, so the honest answer here is "nothing".
		// A restore that resurrects categories the user still has would be the bug.
		await page.getByRole('button', { name: 'Restore default categories' }).click();

		await expect(page.getByText('Nothing was missing.')).toBeVisible();
	});

	test('links out to the desk app', async ({ page }) => {
		await expect(
			page.getByRole('link', { name: /Open full app/ }),
		).toHaveAttribute('href', '/app/wallet');
	});
});
