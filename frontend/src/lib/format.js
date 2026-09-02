// Indian number formatting: lakh and crore grouping, not thousands.
// 1234567 renders as 12,34,567 — anything else looks wrong to an Indian reader.

const inr = new Intl.NumberFormat("en-IN", {
	style: "currency",
	currency: "INR",
	minimumFractionDigits: 2,
	maximumFractionDigits: 2,
});

const inrCompact = new Intl.NumberFormat("en-IN", {
	style: "currency",
	currency: "INR",
	maximumFractionDigits: 0,
});

export function money(value, { compact = false } = {}) {
	const n = Number(value || 0);
	return compact ? inrCompact.format(n) : inr.format(n);
}

/** Magnitude only — the sign is carried by colour and an explicit +/− prefix. */
export function moneyAbs(value, options) {
	return money(Math.abs(Number(value || 0)), options);
}

export function signed(value, options) {
	const n = Number(value || 0);
	const prefix = n > 0 ? "+" : n < 0 ? "−" : "";
	return prefix + moneyAbs(n, options);
}

const dayMonth = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
const fullDate = new Intl.DateTimeFormat("en-IN", {
	day: "numeric",
	month: "short",
	year: "numeric",
});

function toDate(value) {
	if (!value) return null;
	// Frappe hands back "YYYY-MM-DD"; parsing that directly is UTC-shifted in some
	// browsers, so build the date from parts.
	const [y, m, d] = String(value).slice(0, 10).split("-").map(Number);
	if (!y || !m || !d) return null;
	return new Date(y, m - 1, d);
}

export function formatDate(value, { withYear = false } = {}) {
	const date = toDate(value);
	if (!date) return "";
	return withYear ? fullDate.format(date) : dayMonth.format(date);
}

/** "Today" / "Yesterday" / "12 Mar" — used as transaction group headings. */
export function relativeDay(value) {
	const date = toDate(value);
	if (!date) return "";

	const today = new Date();
	today.setHours(0, 0, 0, 0);
	const diff = Math.round((today - date) / 86400000);

	if (diff === 0) return "Today";
	if (diff === 1) return "Yesterday";
	if (date.getFullYear() !== today.getFullYear()) return formatDate(value, { withYear: true });
	return formatDate(value);
}

/**
 * A local calendar date as "YYYY-MM-DD", the format Frappe stores dates in.
 *
 * Deliberately not `toISOString()`: that converts to UTC first, so a transaction filed
 * from India before 05:30 would be dated yesterday — and dated wrong is worse than no
 * default at all, because it is the one field a person skims past.
 */
export function isoDate(date = new Date()) {
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
		date.getDate()
	).padStart(2, "0")}`;
}

export function monthRange(offset = 0) {
	const now = new Date();
	const start = new Date(now.getFullYear(), now.getMonth() + offset, 1);
	const end = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
	return {
		from: isoDate(start),
		to: isoDate(end),
		label: start.toLocaleString("en-IN", { month: "long" }),
	};
}
