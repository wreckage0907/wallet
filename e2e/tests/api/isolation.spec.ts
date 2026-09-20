import { expect, test } from '@playwright/test';
import {
	CREDIT_CARD,
	E2E_OTHER_USER,
	E2E_PASSWORD,
	NET_WORTH,
	OTHER_ACCOUNT,
	OTHER_SECRET_LABEL,
	SAVINGS,
	callGet,
	callPost,
	getDocResponse,
	getList,
	isoDate,
	loggedInUser,
} from '../../helpers';

/**
 * Owner isolation, asserted at the API rather than through the UI.
 *
 * `wallet/permissions.py` enforces it in three places — `if_owner` in the doctype
 * permissions, `permission_query_conditions`, and `has_permission`. A PWA screen only
 * exercises whichever one its particular query happens to hit; going straight at
 * `/api/resource` covers the list path and the single-document path separately, which is
 * where the two failure modes actually differ.
 *
 * The other holder's docnames are discovered by logging in as them in a second request
 * context, so nothing here depends on a hash docname being written down somewhere.
 */
test.describe('Owner isolation', () => {
	test('the suite is not running as Administrator', async ({ request }) => {
		// Administrator is exempt from isolation, so this guard is what stops every
		// assertion below from passing for the wrong reason.
		expect(await loggedInUser(request)).not.toBe('Administrator');
	});

	test('listing accounts returns only this user\'s', async ({ request }) => {
		const accounts = await getList<{ account_name: string }>(
			request,
			'Wallet Account',
			{ fields: ['name', 'account_name'] },
		);
		const names = accounts.map((a) => a.account_name);

		expect(names).toContain(SAVINGS);
		expect(names).toContain(CREDIT_CARD);
		expect(names).not.toContain(OTHER_ACCOUNT);
	});

	test('listing transactions returns only this user\'s', async ({ request }) => {
		const transactions = await getList<{ description: string }>(
			request,
			'Wallet Transaction',
			{ fields: ['name', 'description'] },
		);
		const descriptions = transactions.map((t) => t.description);

		expect(descriptions).toContain('E2E Coffee Shop');
		expect(descriptions).not.toContain(OTHER_SECRET_LABEL);
	});

	test('the overview aggregate covers only this user\'s accounts', async ({
		request,
	}) => {
		// The canary account holds the largest balance in the dataset. If the SUM ever
		// escaped its owner condition, net worth would be wrong by that amount — an
		// aggregate leak that no per-row assertion would notice.
		const overview = await callGet<{
			net_worth: number;
			accounts: { account_name: string }[];
		}>(request, 'wallet.api.balance.get_overview');

		expect(overview.net_worth).toBeCloseTo(NET_WORTH, 2);
		expect(overview.accounts.map((a) => a.account_name)).not.toContain(
			OTHER_ACCOUNT,
		);
	});

	test.describe('against the other holder\'s own docnames', () => {
		let otherAccount: string;
		let otherTransaction: string;

		test.beforeAll(async ({ playwright, baseURL }) => {
			const context = await playwright.request.newContext({ baseURL });
			await context.post('/api/method/login', {
				form: { usr: E2E_OTHER_USER, pwd: E2E_PASSWORD },
			});

			[otherAccount] = (
				await getList<{ name: string }>(context, 'Wallet Account', {
					fields: ['name'],
				})
			).map((a) => a.name);
			[otherTransaction] = (
				await getList<{ name: string }>(context, 'Wallet Transaction', {
					fields: ['name'],
				})
			).map((t) => t.name);

			await context.dispose();

			expect(otherAccount, 'other holder has a seeded account').toBeTruthy();
			expect(
				otherTransaction,
				'other holder has a seeded transaction',
			).toBeTruthy();
		});

		test('reading their account by name is refused', async ({ request }) => {
			const response = await getDocResponse(
				request,
				'Wallet Account',
				otherAccount,
			);

			expect(response.ok()).toBeFalsy();
			expect([403, 404]).toContain(response.status());
		});

		test('reading their transaction by name is refused', async ({
			request,
		}) => {
			const response = await getDocResponse(
				request,
				'Wallet Transaction',
				otherTransaction,
			);

			expect(response.ok()).toBeFalsy();
			expect([403, 404]).toContain(response.status());
		});

		test('a transaction cannot be posted onto their account', async ({
			request,
		}) => {
			// The PWA's Add screen writes through this endpoint, and the account it posts is
			// whatever id the caller sends. `doc.insert()` checks only that *this* user may
			// create a transaction, and Frappe's link validation checks only that the
			// account row exists — neither notices it belongs to somebody else. The
			// explicit `frappe.has_permission` in `transaction_api` is the whole defence.
			await expect(
				callPost(request, 'wallet.api.transaction_api.create_transaction', {
					account: otherAccount,
					posting_date: isoDate(),
					direction: 'Out',
					amount: 1,
					description: 'E2E isolation probe',
				}),
			).rejects.toThrow();

			// And nothing landed: a write refused after the insert would be just as bad as
			// one allowed, since the row would be sitting in the other holder's account.
			const probes = await getList(request, 'Wallet Transaction', {
				fields: ['name'],
				filters: [['description', '=', 'E2E isolation probe']],
			});
			expect(probes).toHaveLength(0);
		});

		test('their balance is not readable by guessing the docname', async ({
			request,
		}) => {
			// `get_account_balance` reads the opening balance with `frappe.db.get_value`,
			// which bypasses the permission hooks entirely. Its explicit
			// `frappe.has_permission` check is the only thing closing that hole, and this
			// is the test that keeps it there.
			await expect(
				callGet(request, 'wallet.api.balance.get_account_balance', {
					account: otherAccount,
				}),
			).rejects.toThrow();
		});
	});
});
