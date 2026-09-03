import { useRef } from "react";
import { Loader2 } from "lucide-react";

import { serverMessage } from "../lib/api.js";

export function Card({ children, className = "", ...rest }) {
	return (
		<div
			className={`rounded-2xl border p-4 ${className}`}
			style={{ background: "var(--surface)", borderColor: "var(--border)" }}
			{...rest}
		>
			{children}
		</div>
	);
}

export function Screen({ title, action, children }) {
	return (
		<>
			<header className="safe-top sticky top-0 z-40 px-4 pt-3 pb-2 backdrop-blur"
				style={{ background: "color-mix(in srgb, var(--surface-sunken) 88%, transparent)" }}>
				<div className="flex items-center justify-between gap-3">
					<h1 className="text-2xl font-bold tracking-tight">{title}</h1>
					{action}
				</div>
			</header>
			<div className="space-y-3 px-4 pt-1">{children}</div>
		</>
	);
}

export function Spinner({ label = "Loading" }) {
	return (
		<div
			className="flex items-center justify-center gap-2 py-12 text-sm"
			style={{ color: "var(--text-muted)" }}
		>
			<Loader2 size={16} className="animate-spin" />
			{label}
		</div>
	);
}

export function EmptyState({ icon: Icon, title, hint, action }) {
	return (
		<div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
			{Icon && (
				<span
					className="flex h-12 w-12 items-center justify-center rounded-2xl"
					style={{ background: "var(--surface-raised)", color: "var(--text-muted)" }}
				>
					<Icon size={22} />
				</span>
			)}
			<p className="font-semibold">{title}</p>
			{hint && (
				<p className="max-w-xs text-sm" style={{ color: "var(--text-muted)" }}>
					{hint}
				</p>
			)}
			{action}
		</div>
	);
}

export function ErrorNote({ error, title = "Could not load" }) {
	if (!error) return null;

	return (
		// `role="alert"` because this card is inserted, not revealed: a save that fails
		// while focus is still on the Save button is otherwise silent to a screen reader.
		<Card role="alert" className="text-sm" style={{ borderColor: "var(--color-money-out)" }}>
			<p className="font-semibold" style={{ color: "var(--color-money-out)" }}>
				{title}
			</p>
			<p className="mt-1" style={{ color: "var(--text-muted)" }}>
				{serverMessage(error).slice(0, 300)}
			</p>
		</Card>
	);
}

// Shared by every control below so a select, an input and a button all line up and all
// clear the 44px minimum touch target. Colours come from the CSS variables in index.css,
// which is what makes the form follow the OS between light and dark.
const CONTROL = "min-h-[44px] w-full rounded-xl border px-3 text-base outline-none";
const controlStyle = {
	background: "var(--surface-raised)",
	borderColor: "var(--border)",
	color: "var(--text)",
};

/**
 * A labelled control.
 *
 * The hint sits outside the `<label>` on purpose. Nested inside it, it becomes part of
 * the control's accessible name, and a screen reader announces the whole sentence every
 * time focus lands on the field. Callers that pass a hint wire it up as a description
 * instead, with `aria-describedby={`${id}-hint`}`.
 */
export function Field({ label, hint, htmlFor, children }) {
	return (
		<div>
			<label
				htmlFor={htmlFor}
				className="mb-1 block text-xs font-medium"
				style={{ color: "var(--text-muted)" }}
			>
				{label}
			</label>
			{children}
			{hint && (
				<p
					id={htmlFor ? `${htmlFor}-hint` : undefined}
					className="mt-1 text-xs"
					style={{ color: "var(--text-muted)" }}
				>
					{hint}
				</p>
			)}
		</div>
	);
}

export function TextInput({ className = "", ...rest }) {
	// `text-base` is not a style choice: iOS Safari zooms the whole page in on focus for
	// anything under 16px, and never zooms back out.
	return <input className={`${CONTROL} ${className}`} style={controlStyle} {...rest} />;
}

export function Select({ className = "", children, ...rest }) {
	return (
		<select className={`${CONTROL} ${className}`} style={controlStyle} {...rest}>
			{children}
		</select>
	);
}

/**
 * A two-way choice rendered as one control rather than two radios.
 *
 * Native radio inputs are the semantically obvious answer and the wrong shape on a phone:
 * the hit target is the dot, not the label. These are buttons in a `radiogroup` instead,
 * which means the keyboard behaviour a real radio group gets for free has to be built:
 *
 * - **one tab stop, not one per option.** Only the selected button is reachable with Tab
 *   (roving `tabIndex`); Tab from inside the group leaves it, rather than walking through
 *   options one at a time.
 * - **arrows move the selection**, wrapping at both ends, with Home and End for the first
 *   and last. Selection follows focus, which is the expected behaviour for a radio group
 *   small enough that every option is visible.
 */
export function Segmented({ value, onChange, options, label }) {
	const refs = useRef([]);
	const index = Math.max(
		options.findIndex((option) => option.value === value),
		0
	);

	const moveTo = (next) => {
		const wrapped = (next + options.length) % options.length;
		onChange(options[wrapped].value);
		refs.current[wrapped]?.focus();
	};

	const onKeyDown = (event) => {
		const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];

		if (step) moveTo(index + step);
		else if (event.key === "Home") moveTo(0);
		else if (event.key === "End") moveTo(options.length - 1);
		else return;

		// Only once a key was actually handled: swallowing everything else would break
		// Tab out of the group and typing into the field below.
		event.preventDefault();
	};

	return (
		<div
			role="radiogroup"
			aria-label={label}
			className="flex gap-1 rounded-xl border p-1"
			style={{ background: "var(--surface-raised)", borderColor: "var(--border)" }}
		>
			{options.map((option, i) => {
				const active = option.value === value;
				return (
					<button
						key={option.value}
						ref={(node) => {
							refs.current[i] = node;
						}}
						type="button"
						role="radio"
						aria-checked={active}
						tabIndex={i === index ? 0 : -1}
						onKeyDown={onKeyDown}
						onClick={() => onChange(option.value)}
						className="min-h-[40px] flex-1 rounded-lg text-sm font-semibold transition-colors"
						style={{
							background: active ? "var(--surface)" : "transparent",
							color: active ? option.color || "var(--text)" : "var(--text-muted)",
							boxShadow: active ? "0 1px 2px rgb(0 0 0 / 0.08)" : "none",
						}}
					>
						{option.label}
					</button>
				);
			})}
		</div>
	);
}
