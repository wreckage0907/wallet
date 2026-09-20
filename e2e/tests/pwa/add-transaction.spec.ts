import { expect, test } from '@playwright/test';
import {
	MANUAL_AMOUNT,
	MANUAL_DESCRIPTION,
	MANUAL_PREFIX,
	MANUAL_REFERENCE,
	MANUAL_SAVINGS_BALANCE,
	SAVINGS,
	appUrl,
	deleteDoc,
	getList,
	money,
} from '../../helpers';

/**
 * The PWA's write path, end to end: form → `wallet.api.transaction_api` → the list.
 *
 * The only spec in the suite that writes anything, so it is also the only one that has to
 * clean up. Everything it creates carries `MANUAL_PREFIX` in its description, and the
 * `afterEach` deletes every row matching that — the seeded balances are asserted to the
 * rupee elsewhere, and Playwright runs these files alphabetically, so a leftover row
 * would fail `dashboard.spec.ts` rather than anything here.
 */
test.describe('Adding a transaction', () => {
	test.afterEach(async ({ request }) => {
		const written = await getList<{ name: string }>(request, 'Wallet Transaction', {
			fields: ['name'],
			filters: [['description', 'like', `${MANUAL_PREFIX}%`]],
		});

		for (const row of written) {
			await deleteDoc(request, 'Wallet Transaction', row.name);
		}
	});

	async function fillTheForm(
		page: import('@playwright/test').Page,
		{ description = MANUAL_DESCRIPTION, amount = MANUAL_AMOUNT, reference = '' } = {},
	) {
		await page.goto(appUrl('add'));
		await expect(page.getByRole('heading', { name: 'Add' })).toBeVisible();

		await page.getByLabel('Amount').fill(String(amount));
		await page.getByLabel('Account').selectOption({ label: SAVINGS });
		await page.getByLabel('Description').fill(description);

		if (reference) {
			await page.getByRole('button', { name: 'More details' }).click();
			await page.getByLabel('Reference number').fill(reference);
		}
	}

	test('the Add tab opens the form', async ({ page }) => {
		await page.goto(appUrl());
		await page.locator('nav').getByRole('link', { name: 'Add' }).click();

		await expect(page).toHaveURL(new RegExp(`${appUrl('add')}$`));
		await expect(page.getByLabel('Amount')).toBeVisible();
	});

	test('records a spend and reports the balance it leaves behind', async ({
		page,
	}) => {
		await fillTheForm(page);
		await page.getByRole('button', { name: /Save spend/ }).click();

		await expect(page.getByRole('heading', { name: 'Added' })).toBeVisible();
		await expect(page.getByText(`−${money(MANUAL_AMOUNT)}`)).toBeVisible();

		// The balance echo is the point of the whole endpoint: it is where a misread amount
		// becomes visible. Getting it right means the sign convention survived insert ->
		// signed_amount -> SUM -> the response.
		await expect(
			page.getByText(money(MANUAL_SAVINGS_BALANCE), { exact: false }),
		).toBeVisible();
	});

	test('the saved transaction shows up in Activity', async ({ page }) => {
		await fillTheForm(page);
		await page.getByRole('button', { name: /Save spend/ }).click();
		await expect(page.getByRole('heading', { name: 'Added' })).toBeVisible();

		await page.getByRole('button', { name: 'View activity' }).click();

		await expect(page).toHaveURL(new RegExp(`${appUrl('transactions')}$`));
		await expect(page.getByText(MANUAL_DESCRIPTION)).toBeVisible();
	});

	test('money received is recorded as an incoming amount', async ({ page }) => {
		await fillTheForm(page, { description: `${MANUAL_PREFIX} Refund` });
		await page.getByRole('radio', { name: 'Received' }).click();
		await page.getByRole('button', { name: /Save income/ }).click();

		await expect(page.getByText(`+${money(MANUAL_AMOUNT)}`)).toBeVisible();
	});

	test('Save stays disabled until there is an amount', async ({ page }) => {
		await page.goto(appUrl('add'));

		const save = page.getByRole('button', { name: /Save spend/ });
		await expect(save).toBeDisabled();

		await page.getByLabel('Amount').fill(String(MANUAL_AMOUNT));
		await expect(save).toBeEnabled();
	});

	test('a repeated reference number is refused by name, not by SQL error', async ({
		page,
	}) => {
		// `dedup_hash` is UNIQUE. Without the server's pre-check this second save reaches
		// the user as a MariaDB 1062, which is the failure this whole path exists to avoid.
		await fillTheForm(page, { reference: MANUAL_REFERENCE });
		await page.getByRole('button', { name: /Save spend/ }).click();
		await expect(page.getByRole('heading', { name: 'Added' })).toBeVisible();

		await fillTheForm(page, { reference: MANUAL_REFERENCE });
		await page.getByRole('button', { name: /Save spend/ }).click();

		await expect(page.getByText('Not saved')).toBeVisible();
		await expect(page.getByText(/already recorded/)).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Added' })).toHaveCount(0);
	});

	test('a date before the account opened is refused in words', async ({ page }) => {
		await fillTheForm(page, { description: `${MANUAL_PREFIX} Too Early` });
		await page.getByLabel('Date').fill('2001-01-01');
		await page.getByRole('button', { name: /Save spend/ }).click();

		// Straight from `WalletTransaction.validate_against_opening_date`. Reaching the
		// screen at all means `serverMessage` dug it out of `_server_messages` rather than
		// showing "ValidationError".
		await expect(page.getByText(/opening date/)).toBeVisible();
	});
});
