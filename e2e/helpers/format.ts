/**
 * The app's money formatting, reproduced for assertions.
 *
 * Mirrors `frontend/src/lib/format.js` — Indian lakh/crore grouping, two decimals for
 * the full form and none for the compact one. Asserting on a hard-coded "₹1,52,750.00"
 * would encode both the amount and the locale rules into every spec; going through Intl
 * means only a genuine formatting change breaks a test.
 */

const inr = new Intl.NumberFormat('en-IN', {
	style: 'currency',
	currency: 'INR',
	minimumFractionDigits: 2,
	maximumFractionDigits: 2,
});

const inrCompact = new Intl.NumberFormat('en-IN', {
	style: 'currency',
	currency: 'INR',
	maximumFractionDigits: 0,
});

export function money(value: number, { compact = false } = {}): string {
	return compact ? inrCompact.format(value) : inr.format(value);
}

/** The current month's name, as the dashboard labels its cashflow tiles. */
export function currentMonthLabel(): string {
	const now = new Date();
	return new Date(now.getFullYear(), now.getMonth(), 1).toLocaleString('en-IN', {
		month: 'long',
	});
}
