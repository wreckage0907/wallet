import { expect, test } from '@playwright/test';
import {
	ACCOUNT_DETAIL_URL_RE,
	CARD_BALANCE,
	CREDIT_CARD,
	GROCERIES,
	NET_WORTH,
	OTHER_ACCOUNT,
	SAVINGS,
	SAVINGS_BALANCE,
	appUrl,
	money,
} from '../../helpers';

test.describe('Accounts', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto(appUrl('accounts'));
		await expect(page.getByRole('heading', { name: 'Accounts' })).toBeVisible();
	});

	test('lists every account this user owns, with its balance', async ({
		page,
	}) => {
		await expect(page.getByText(SAVINGS, { exact: true })).toBeVisible();
		await expect(
			page.getByText(money(SAVINGS_BALANCE), { exact: true }),
		).toBeVisible();
		await expect(page.getByText(CREDIT_CARD, { exact: true })).toBeVisible();
	});

	test('a credit card reads as "Outstanding", magnitude not sign', async ({
		page,
	}) => {
		// Held as a negative balance so net worth stays a plain sum; users think of a card
		// as "I owe 4,200", never "minus 4,200", so the card flips the label and drops the
		// sign. Asserting the unsigned figure is what pins that down.
		expect(CARD_BALANCE).toBeLessThan(0);

		const card = page.locator('a', { hasText: CREDIT_CARD });
		await expect(card.getByText('Outstanding')).toBeVisible();
		await expect(card.getByText(money(GROCERIES), { exact: true })).toBeVisible();
	});

	test('the combined figure matches net worth', async ({ page }) => {
		await expect(page.getByText('Combined')).toBeVisible();
		await expect(page.getByText(money(NET_WORTH), { exact: true })).toBeVisible();
	});

	test('never lists the other account holder', async ({ page }) => {
		await expect(page.getByText(OTHER_ACCOUNT)).toHaveCount(0);
	});

	test('opening an account shows its balance and its transactions', async ({
		page,
	}) => {
		await page.locator('a', { hasText: SAVINGS }).click();

		await expect(page).toHaveURL(ACCOUNT_DETAIL_URL_RE);
		await expect(page.getByRole('heading', { name: SAVINGS })).toBeVisible();
		await expect(page.getByText('Balance', { exact: true })).toBeVisible();
		await expect(page.getByText('E2E Coffee Shop')).toBeVisible();
		await expect(page.getByText('E2E Landlord')).toBeVisible();

		// The card's transaction belongs to a different account and must not appear here.
		await expect(page.getByText('E2E Supermarket')).toHaveCount(0);
	});

	test('back returns to the accounts list', async ({ page }) => {
		await page.locator('a', { hasText: SAVINGS }).click();
		await expect(page).toHaveURL(ACCOUNT_DETAIL_URL_RE);

		await page.getByRole('link', { name: 'Back to accounts' }).click();
		await expect(page).toHaveURL(new RegExp(`${appUrl('accounts')}$`));
	});
});
