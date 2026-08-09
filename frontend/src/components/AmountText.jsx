import { moneyAbs } from "../lib/format.js";

/**
 * Money with the sign carried by colour *and* an explicit +/− glyph.
 * Colour alone would be invisible to a colour-blind reader.
 */
export default function AmountText({ value, direction, className = "", compact = false }) {
	const n = Number(value || 0);
	const isIn = direction ? direction === "In" : n >= 0;

	return (
		<span
			className={`tnum font-semibold ${className}`}
			style={{ color: isIn ? "var(--color-money-in)" : "var(--color-money-out)" }}
		>
			{isIn ? "+" : "−"}
			{moneyAbs(n, { compact })}
		</span>
	);
}
