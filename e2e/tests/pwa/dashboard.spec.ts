import { expect, test } from '@playwright/test';
import {
	APP_BASE,
	CREDIT_CARD,
	MONTH_IN,
	MONTH_OUT,
	NET_WORTH,
	OTHER_SECRET_LABEL,
	SAVINGS,
	appUrl,
	currentMonthLabel,
	money,
} from '../../helpers';

test.describe('Dashboard', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto(APP_BASE);
		await expect(page.getByRole('heading', { name: 'Wallet' })).toBeVisible();
	});

	test('net worth is the plain sum of every account balance', async ({
		page,
	}) => {
		// The seeded card balance is negative, so this figure only comes out right if the
		// sign convention survives the whole path: insert -> signed_amount -> SUM ->
		// get_overview -> render.
		await expect(page.getByText(money(NET_WORTH), { exact: true })).toBeVisible();
	});

	test('a liability is reported as owed, not as a negative asset', async ({
		page,
	}) => {
		await expect(page.getByText('Assets', { exact: false })).toBeVisible();
		await expect(page.getByText('Owed', { exact: false })).toBeVisible();
	});

	test('the cashflow tiles cover the current month', async ({ page }) => {
		const month = currentMonthLabel();

		await expect(page.getByText(`In · ${month}`)).toBeVisible();
		await expect(page.getByText(`Out · ${month}`)).toBeVisible();
		await expect(
			page.getByText(money(MONTH_IN, { compact: true }), { exact: true }),
		).toBeVisible();
		await expect(
			page.getByText(money(MONTH_OUT, { compact: true }), { exact: true }),
		).toBeVisible();
	});

	test('lists the seeded accounts and recent activity', async ({ page }) => {
		await expect(page.getByText(SAVINGS, { exact: true })).toBeVisible();
		await expect(page.getByText(CREDIT_CARD, { exact: true })).toBeVisible();
		await expect(page.getByText('E2E Coffee Shop').first()).toBeVisible();
	});

	test('shows nothing belonging to the other account holder', async ({
		page,
	}) => {
		// The canary is the largest amount in the dataset: if it ever leaked it would move
		// net worth too, so this assertion and the one above fail together.
		await expect(page.getByText(OTHER_SECRET_LABEL)).toHaveCount(0);
	});

	test('"See all" goes to the accounts screen', async ({ page }) => {
		await page
			.getByRole('link', { name: 'See all' })
			.first()
			.click();

		await expect(page).toHaveURL(new RegExp(`${appUrl('accounts')}$`));
		await expect(page.getByRole('heading', { name: 'Accounts' })).toBeVisible();
	});
});
