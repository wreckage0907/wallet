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

/**
 * A local calendar date as "YYYY-MM-DD", the way the app's own `isoDate` builds one.
 *
 * Not `toISOString()`, for the same reason: that converts to UTC first, and the suite
 * already goes to some trouble (see `timezoneId` in playwright.config.ts) to keep the
 * browser and the site agreeing on what today is.
 */
export function isoDate(date = new Date()): string {
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
		date.getDate(),
	).padStart(2, '0')}`;
}
