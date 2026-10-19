import { useRef } from "react";

import {
	Alert,
	Button as FrappeButton,
	DatePicker,
	LoadingIndicator,
} from "@rtcamp/frappe-ui-react";

import { serverMessage } from "../lib/api.js";

// Re-export the Frappe UI controls the pages reach for directly that need no wrapping.
//
// `Label` is deliberately not re-exported: the library's Label wraps Base UI's
// `Field.Label`, which only works inside a `Field.Root` and throws #28 standalone.
export { Alert, DatePicker };

/**
 * The library's interactive controls get thin wrappers instead of a bare re-export, for
 * two reasons:
 *
 * - its largest input/select/button is h-10 (40px), under the app's 44px touch-target
 *   minimum (see BottomNav), and
 * - its `Select` does not forward ARIA props such as `aria-describedby` to the native
 *   `<select>`.
 *
 * The wrappers render the native elements styled with Frappe UI tokens, so every
 * attribute passes straight through and every control clears 44px.
 */
const CONTROL =
	"min-h-[44px] w-full rounded-lg border border-outline-gray-2 bg-surface-gray-2 px-3 text-base text-ink-gray-9 outline-none";

export function Button({ className = "", ...rest }) {
	return <FrappeButton {...rest} className={`min-h-[44px] ${className}`} />;
}

export function TextInput({ className = "", ...rest }) {
	// `text-base` is not a style choice: iOS Safari zooms the whole page in on focus for
	// anything under 16px, and never zooms back out.
	return <input className={`${CONTROL} ${className}`} {...rest} />;
}

export function Select({ className = "", options = [], placeholder, ...rest }) {
	return (
		<select className={`${CONTROL} ${className}`} {...rest}>
			{placeholder ? <option value="">{placeholder}</option> : null}
			{options.map((option) => {
				const { value, label, disabled } =
					typeof option === "string" ? { value: option, label: option } : option;
				return (
					<option key={value} value={value} disabled={disabled}>
						{label}
					</option>
				);
			})}
		</select>
	);
}

/**
 * A bare Frappe UI surface.
 *
 * Deliberately not frappe-ui-react's own `Card`: that one is a titled card that always
 * renders an (empty) heading row and wraps its children in an `overflow-auto` area, and
 * it paints `bg-white` instead of the semantic surface token, so it never follows dark
 * mode. These screens need a plain sheet, so we build one from the tokens directly.
 */
export function Card({ className = "", ...rest }) {
	return (
		<div
			className={`rounded-lg border border-outline-gray-2 bg-surface-white p-4 text-ink-gray-9 shadow-sm ${className}`}
			{...rest}
		/>
	);
}

export function Screen({ title, action, children }) {
	return (
		<>
			<header className="safe-top sticky top-0 z-40 bg-surface-gray-1 px-4 pt-3 pb-2">
				<div className="flex items-center justify-between gap-3">
					<h1 className="text-2xl font-semibold tracking-tight text-ink-gray-9">{title}</h1>
					{action}
				</div>
			</header>
			<div className="space-y-3 px-4 pt-1">{children}</div>
		</>
	);
}

export function Spinner({ label = "Loading" }) {
	return (
		<div className="flex items-center justify-center gap-2 py-12 text-sm text-ink-gray-5">
			<LoadingIndicator className="h-4 w-4" />
			{label}
		</div>
	);
}

export function EmptyState({ icon: Icon, title, hint, action }) {
	return (
		<div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
			{Icon && (
				<span className="flex h-12 w-12 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-5">
					<Icon size={22} />
				</span>
			)}
			<p className="text-base font-medium text-ink-gray-9">{title}</p>
			{hint && <p className="max-w-xs text-sm text-ink-gray-5">{hint}</p>}
			{action}
		</div>
	);
}

export function ErrorNote({ error, title = "Could not load" }) {
	if (!error) return null;

	return (
		// `role="alert"` is built into Frappe UI's Alert; this card is inserted, not
		// revealed, so a save that fails while focus is on the button is announced.
		<Alert theme="red" title={title} renderDescription={serverMessage(error).slice(0, 300)} dismissable={false} />
	);
}

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
			{label && (
				<label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-ink-gray-5">
					{label}
				</label>
			)}
			{children}
			{hint && (
				<p id={htmlFor ? `${htmlFor}-hint` : undefined} className="mt-1 text-xs text-ink-gray-5">
					{hint}
				</p>
			)}
		</div>
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
			className="flex gap-1 rounded-lg border border-outline-gray-2 bg-surface-gray-2 p-1"
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
						className={`min-h-[40px] flex-1 rounded-md text-sm font-medium transition-colors ${
							active ? `bg-surface-white shadow-sm ${option.color || "text-ink-gray-9"}` : "text-ink-gray-5"
						}`}
					>
						{option.label}
					</button>
				);
			})}
		</div>
	);
}
