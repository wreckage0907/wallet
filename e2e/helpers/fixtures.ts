/**
 * The fixture contract, mirroring `wallet/tests/e2e_seed.py`.
 *
 * There is no automatic mechanism keeping the two in step — the seed is Python run by
 * bench, the specs are TypeScript run by Playwright. Every literal a spec asserts on
 * lives in one of these two files and nowhere else, so a drift is a one-file diff rather
 * than a hunt through thirty specs.
 */

export const E2E_USER = process.env.WALLET_E2E_USER || 'wallet-e2e@example.com';
export const E2E_PASSWORD =
	process.env.WALLET_E2E_PASSWORD || 'wallet-e2e-password';
export const E2E_OTHER_USER =
	process.env.WALLET_E2E_OTHER_USER || 'wallet-e2e-other@example.com';

export const SAVINGS = 'E2E Savings';
export const CREDIT_CARD = 'E2E Credit Card';
export const OTHER_ACCOUNT = 'E2E Other Holder Account';

export const SAVINGS_OPENING = 100000;
export const SALARY = 85000;
export const COFFEE = 250;
export const RENT = 32000;
export const GROCERIES = 4200;

/** The other holder's canary — must never surface in this user's session. */
export const OTHER_SECRET_LABEL = 'E2E Other Holder Secret Spend';

export const SAVINGS_BALANCE = SAVINGS_OPENING + SALARY - COFFEE - RENT;
export const CARD_BALANCE = -GROCERIES;
export const NET_WORTH = SAVINGS_BALANCE + CARD_BALANCE;

/** Money in / out for the current month, as the dashboard tiles compute them. */
export const MONTH_IN = SALARY;
export const MONTH_OUT = COFFEE + RENT + GROCERIES;
