import { expect, test } from '@playwright/test';
import { DESK_WORKSPACE, OTHER_ACCOUNT, SAVINGS } from '../../helpers';

/**
 * The desk half of the app. The PWA is read-only, so every create and edit still happens
 * here — which makes "does the workspace render for a plain Wallet User" a load-bearing
 * question rather than a cosmetic one.
 */
test.describe('Desk workspace', () => {
	test('renders for a Wallet User', async ({ page }) => {
		await page.goto(DESK_WORKSPACE);
		await page.waitForLoadState('networkidle');

		// Asserted on the workspace's own shortcuts rather than on a page heading: v16
		// serves the desk under /desk (with /app redirecting) and renders the workspace
		// title as plain chrome, which is Frappe's to restyle and not ours to pin down.
		// The shortcuts come from wallet/wallet/workspace/wallet/wallet.json, so they are.
		await expect(
			page.getByRole('link', { name: /^Wallet Account/ }).first(),
		).toBeVisible();
		await expect(
			page.getByRole('link', { name: /^Wallet Transaction/ }).first(),
		).toBeVisible();
		await expect(
			page.getByRole('link', { name: /^Import Statement/ }).first(),
		).toBeVisible();
	});

	test('the account list shows this user\'s accounts only', async ({ page }) => {
		await page.goto('/app/wallet-account');
		await page.waitForLoadState('networkidle');

		await expect(page.getByText(SAVINGS).first()).toBeVisible();
		await expect(page.getByText(OTHER_ACCOUNT)).toHaveCount(0);
	});

	test('the transaction list shows this user\'s transactions only', async ({
		page,
	}) => {
		await page.goto('/app/wallet-transaction');
		await page.waitForLoadState('networkidle');

		await expect(page.getByText('E2E Coffee Shop').first()).toBeVisible();
		await expect(page.getByText('E2E Other Holder Secret Spend')).toHaveCount(0);
	});
});
