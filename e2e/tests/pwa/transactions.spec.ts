import { expect, test } from '@playwright/test';
import { OTHER_SECRET_LABEL, appUrl } from '../../helpers';

test.describe('Activity', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto(appUrl('transactions'));
		await expect(page.getByRole('heading', { name: 'Activity' })).toBeVisible();
	});

	test('groups transactions by day', async ({ page }) => {
		// Today's two rows are seeded with today's date, so the diary heading has to read
		// "Today" rather than a formatted date.
		await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
		await expect(page.getByText('E2E Coffee Shop')).toBeVisible();
		await expect(page.getByText('E2E Employer')).toBeVisible();
	});

	test('the Spent filter keeps outgoings only', async ({ page }) => {
		await page.getByRole('button', { name: 'Spent' }).click();

		await expect(page.getByText('E2E Coffee Shop')).toBeVisible();
		await expect(page.getByText('E2E Landlord')).toBeVisible();
		await expect(page.getByText('E2E Employer')).toHaveCount(0);
	});

	test('the Received filter keeps incomings only', async ({ page }) => {
		await page.getByRole('button', { name: 'Received' }).click();

		await expect(page.getByText('E2E Employer')).toBeVisible();
		await expect(page.getByText('E2E Coffee Shop')).toHaveCount(0);
	});

	test('All restores the unfiltered list', async ({ page }) => {
		await page.getByRole('button', { name: 'Spent' }).click();
		await expect(page.getByText('E2E Employer')).toHaveCount(0);

		await page.getByRole('button', { name: 'All' }).click();
		await expect(page.getByText('E2E Employer')).toBeVisible();
		await expect(page.getByText('E2E Coffee Shop')).toBeVisible();
	});

	test('never shows the other account holder\'s transactions', async ({
		page,
	}) => {
		// The list is the widest read surface in the app — no account filter, every row the
		// query will hand back. If owner isolation breaks anywhere, it shows here first.
		await expect(page.getByText(OTHER_SECRET_LABEL)).toHaveCount(0);

		await page.getByRole('button', { name: 'Spent' }).click();
		await expect(page.getByText(OTHER_SECRET_LABEL)).toHaveCount(0);
	});
});
