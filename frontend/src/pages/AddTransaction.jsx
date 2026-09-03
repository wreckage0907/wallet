import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Check, ChevronLeft, Loader2, Wallet2 } from "lucide-react";
import { useSWRConfig } from "frappe-react-sdk";

import { Card, EmptyState, ErrorNote, Field, Screen, Segmented, Select, TextInput } from "../components/ui.jsx";
import { currencySymbol, formatDate, isoDate, money } from "../lib/format.js";
import { useAccountOptions, useCategoryOptions, useCreateTransaction } from "../lib/api.js";

/**
 * The PWA's only write path.
 *
 * Everything else in `/wallet` reads; adding a transaction used to mean the desk form,
 * on a phone, which is the one context the desk is worst at.
 *
 * The screen is built around the two fields that are actually hard to get right on a
 * phone — the amount and which way the money went — and pushes the rest down. Amount is
 * the hero because it is the field a mis-tap ruins silently: a wrong description is
 * obvious forever, a wrong digit looks exactly like a right one.
 */

const DIRECTIONS = [
	{ value: "Out", label: "Spent", color: "var(--color-money-out)" },
	{ value: "In", label: "Received", color: "var(--color-money-in)" },
];

const PAYMENT_MODES = [
	"UPI",
	"Card",
	"NEFT",
	"IMPS",
	"RTGS",
	"ATM",
	"Cheque",
	"Cash",
	"Auto Debit",
	"Interest",
	"Charges",
	"Other",
];

/** Everything a fresh form starts as, minus the account, which is filled in once loaded. */
const blankForm = () => ({
	direction: "Out",
	amount: "",
	account: "",
	posting_date: isoDate(),
	description: "",
	category: "",
	counterparty: "",
	payment_mode: "",
	reference_number: "",
	notes: "",
});

export default function AddTransaction() {
	const navigate = useNavigate();
	const { mutate } = useSWRConfig();

	const {
		data: accounts,
		isLoading: loadingAccounts,
		error: accountsError,
		mutate: reloadAccounts,
	} = useAccountOptions();
	const { data: categories, error: categoriesError } = useCategoryOptions();
	const { call: create, loading: saving } = useCreateTransaction();

	const [form, setForm] = useState(blankForm);
	const [showMore, setShowMore] = useState(false);
	const [error, setError] = useState(null);
	const [saved, setSaved] = useState(null);

	const set = (field) => (event) => setForm((f) => ({ ...f, [field]: event.target.value }));

	// Default to the first account rather than an empty select. There is usually only one
	// plausible answer, and a required field that starts invalid is a trap on a small
	// screen where the Save button and the offending select are rarely visible together.
	useEffect(() => {
		if (!form.account && accounts?.length) {
			setForm((f) => (f.account ? f : { ...f, account: accounts[0].name }));
		}
	}, [accounts, form.account]);

	// Expense categories for money out, income ones for money in. Transfer categories are
	// offered either way — a transfer has a leg in each direction.
	const categoryOptions = useMemo(() => {
		const wanted = form.direction === "In" ? "Income" : "Expense";
		return (categories || []).filter(
			(row) => row.category_type === wanted || row.category_type === "Transfer"
		);
	}, [categories, form.direction]);

	// A category chosen for one direction can be nonsense for the other, so drop it when
	// the direction flips rather than silently posting "Salary" against a payment.
	useEffect(() => {
		if (form.category && !categoryOptions.some((row) => row.name === form.category)) {
			setForm((f) => ({ ...f, category: "" }));
		}
	}, [categoryOptions, form.category]);

	const amount = Number(form.amount);
	const canSave = form.account && form.posting_date && amount > 0 && !saving;

	// Accounts carry their own currency and the server records the amount in whichever one
	// the chosen account holds, so a hard-coded ₹ would mislabel a non-INR entry at the one
	// moment the number is being typed.
	const currency = accounts?.find((row) => row.name === form.account)?.currency || "INR";

	const submit = async (event) => {
		event.preventDefault();
		setError(null);

		try {
			const response = await create({
				account: form.account,
				posting_date: form.posting_date,
				direction: form.direction,
				amount,
				description: form.description || null,
				category: form.category || null,
				counterparty: form.counterparty || null,
				payment_mode: form.payment_mode || null,
				reference_number: form.reference_number || null,
				notes: form.notes || null,
			});

			const result = response?.message;

			// Not an error: the server refuses a fingerprint collision by name so it can be
			// shown as "you already recorded this", which is a fact, not a failure.
			if (!result?.created) {
				setError({
					message: `This looks like one you have already recorded${
						result?.duplicate_of?.posting_date
							? ` on ${formatDate(result.duplicate_of.posting_date, { withYear: true })}`
							: ""
					}. Nothing was saved.`,
				});
				return;
			}

			// Every balance, list and cashflow tile in the app is now stale. Revalidating by
			// key filter rather than naming them keeps this from going quietly out of date
			// the next time a screen starts fetching something new.
			mutate(() => true);
			setSaved(result);
		} catch (caught) {
			setError(caught);
		}
	};

	const addAnother = () => {
		// Account and date carry over: someone entering yesterday's cash spending is
		// entering several, all on the same account and the same day.
		setSaved(null);
		setError(null);
		setForm((f) => ({ ...blankForm(), account: f.account, posting_date: f.posting_date }));
	};

	if (loadingAccounts && !accounts) {
		return (
			<Screen title="Add">
				<div className="flex items-center justify-center gap-2 py-12 text-sm" style={{ color: "var(--text-muted)" }}>
					<Loader2 size={16} className="animate-spin" /> Loading
				</div>
			</Screen>
		);
	}

	// Before the empty state, not after: a failed request also arrives as no accounts, and
	// "No accounts yet" is a confident lie about someone who has several.
	if (accountsError) {
		return (
			<Screen title="Add">
				<ErrorNote error={accountsError} title="Could not load your accounts" />
				<button
					onClick={() => reloadAccounts()}
					className="min-h-[48px] w-full rounded-2xl border text-sm font-semibold"
					style={{ borderColor: "var(--border)", color: "var(--text)" }}
				>
					Try again
				</button>
			</Screen>
		);
	}

	if (!accounts?.length) {
		return (
			<Screen title="Add">
				<EmptyState
					icon={Wallet2}
					title="No accounts yet"
					hint="A transaction has to be filed against an account. Accounts are set up in the full app."
					action={
						<a
							href="/app/wallet-account/new"
							className="min-h-[44px] rounded-xl px-4 py-3 text-sm font-semibold"
							style={{ background: "var(--brand)", color: "var(--surface)" }}
						>
							Add an account
						</a>
					}
				/>
			</Screen>
		);
	}

	if (saved) {
		const txn = saved.transaction;
		// A liability is held as a negative balance, which is what makes net worth a plain
		// sum. AccountCard and AccountDetail both flip that back for the reader — "I owe
		// 5,200", not "minus 5,200" — and this echo has to agree with them, or the same
		// figure reads two different ways on two screens.
		const account = accounts.find((row) => row.name === txn.account);
		const owes = account?.is_liability && saved.account_balance < 0;

		return (
			<Screen title="Added">
				<Card className="!p-5 text-center">
					<span
						className="mx-auto flex h-12 w-12 items-center justify-center rounded-full"
						style={{ background: "var(--color-money-in)", color: "var(--surface)" }}
					>
						<Check size={24} />
					</span>
					<p className="tnum mt-3 text-2xl font-bold">
						{txn.direction === "In" ? "+" : "−"}
						{money(txn.amount, { currency: txn.currency })}
					</p>
					<p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
						{txn.description || txn.counterparty || "Recorded"} · {txn.account_name}
					</p>
					{/* The balance is the check digit: a mis-typed amount is invisible on its own
					    and obvious the moment it lands next to what the account now holds. */}
					<p className="mt-4 text-xs" style={{ color: "var(--text-muted)" }}>
						{txn.account_name} {owes ? "now owes" : "is now"}{" "}
						<span className="tnum font-semibold" style={{ color: "var(--text)" }}>
							{money(owes ? Math.abs(saved.account_balance) : saved.account_balance, {
								currency: saved.currency,
							})}
						</span>
					</p>
					{txn.category_name && (
						<p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
							Filed under {txn.category_name}
						</p>
					)}
				</Card>

				<div className="grid grid-cols-2 gap-3">
					<button
						onClick={addAnother}
						className="min-h-[48px] rounded-xl border text-sm font-semibold"
						style={{ borderColor: "var(--border)", color: "var(--text)" }}
					>
						Add another
					</button>
					<button
						onClick={() => navigate("/transactions")}
						className="min-h-[48px] rounded-xl text-sm font-semibold"
						style={{ background: "var(--brand)", color: "var(--surface)" }}
					>
						View activity
					</button>
				</div>
			</Screen>
		);
	}

	return (
		<Screen
			title="Add"
			action={
				<Link
					to="/transactions"
					className="flex h-10 items-center gap-1 text-sm font-medium"
					style={{ color: "var(--text-muted)" }}
				>
					<ChevronLeft size={18} /> Cancel
				</Link>
			}
		>
			<form onSubmit={submit} className="space-y-3">
				<Card className="!p-5">
					<Segmented
						label="Direction"
						value={form.direction}
						onChange={(value) => setForm((f) => ({ ...f, direction: value }))}
						options={DIRECTIONS}
					/>

					<div className="mt-4 flex items-center gap-2">
						<span className="text-3xl font-bold" style={{ color: "var(--text-muted)" }}>
							{currencySymbol(currency)}
						</span>
						<input
							id="amount"
							name="amount"
							aria-label="Amount"
							// `inputMode` rather than `type="number"`: a number input on Android accepts
							// "1e3" and reports an empty string for anything it considers malformed, so
							// the field cannot be validated or even read back reliably.
							inputMode="decimal"
							autoComplete="off"
							placeholder="0.00"
							value={form.amount}
							onChange={(event) =>
								setForm((f) => ({ ...f, amount: event.target.value.replace(/[^\d.]/g, "") }))
							}
							className="tnum min-h-[52px] w-full bg-transparent text-4xl font-bold outline-none"
							style={{ color: "var(--text)" }}
						/>
					</div>
				</Card>

				<Card className="space-y-3">
					<Field label="Account" htmlFor="account">
						<Select id="account" name="account" value={form.account} onChange={set("account")}>
							{accounts.map((account) => (
								<option key={account.name} value={account.name}>
									{account.account_name}
								</option>
							))}
						</Select>
					</Field>

					<Field label="Date" htmlFor="posting_date">
						<TextInput
							id="posting_date"
							name="posting_date"
							type="date"
							value={form.posting_date}
							onChange={set("posting_date")}
						/>
					</Field>

					<Field
						label="Description"
						htmlFor="description"
						hint="Kept verbatim — this is what the categorization rules match against."
					>
						<TextInput
							id="description"
							name="description"
							aria-describedby="description-hint"
							type="text"
							placeholder="Coffee at the corner shop"
							value={form.description}
							onChange={set("description")}
						/>
					</Field>

					<Field
						label="Category"
						htmlFor="category"
						hint={
							categoriesError
								? "Categories could not be loaded. Saving without one still works — a rule may fill it in."
								: "Leave blank and a rule may fill it in."
						}
					>
						<Select
							id="category"
							name="category"
							aria-describedby="category-hint"
							value={form.category}
							onChange={set("category")}
						>
							<option value="">Uncategorized</option>
							{categoryOptions.map((category) => (
								<option key={category.name} value={category.name}>
									{category.category_name}
								</option>
							))}
						</Select>
					</Field>
				</Card>

				{/* Collapsed by default. Every field below is one a bank statement fills in for
				    itself; a person typing an entry by hand almost never has them. */}
				<Card className="!p-0 overflow-hidden">
					<button
						type="button"
						onClick={() => setShowMore((open) => !open)}
						aria-expanded={showMore}
						className="min-h-[48px] w-full px-4 text-left text-sm font-medium"
						style={{ color: "var(--text-muted)" }}
					>
						{showMore ? "Fewer details" : "More details"}
					</button>

					{showMore && (
						<div className="space-y-3 border-t px-4 py-4" style={{ borderColor: "var(--border)" }}>
							<Field label="Paid to / from" htmlFor="counterparty">
								<TextInput
									id="counterparty"
									name="counterparty"
									type="text"
									value={form.counterparty}
									onChange={set("counterparty")}
								/>
							</Field>

							<Field label="Payment mode" htmlFor="payment_mode">
								<Select
									id="payment_mode"
									name="payment_mode"
									value={form.payment_mode}
									onChange={set("payment_mode")}
								>
									<option value="">Not recorded</option>
									{PAYMENT_MODES.map((mode) => (
										<option key={mode} value={mode}>
											{mode}
										</option>
									))}
								</Select>
							</Field>

							<Field
								label="Reference number"
								htmlFor="reference_number"
								hint="A UTR or cheque number makes this entry impossible to record twice."
							>
								<TextInput
									id="reference_number"
									name="reference_number"
									aria-describedby="reference_number-hint"
									type="text"
									value={form.reference_number}
									onChange={set("reference_number")}
								/>
							</Field>

							<Field label="Notes" htmlFor="notes">
								<TextInput id="notes" name="notes" type="text" value={form.notes} onChange={set("notes")} />
							</Field>
						</div>
					)}
				</Card>

				{error && <ErrorNote error={error} title="Not saved" />}

				<button
					type="submit"
					disabled={!canSave}
					className="min-h-[52px] w-full rounded-2xl text-base font-semibold transition-opacity disabled:opacity-40"
					style={{ background: "var(--brand)", color: "var(--surface)" }}
				>
					{saving ? "Saving…" : `Save ${form.direction === "In" ? "income" : "spend"}`}
				</button>
			</form>
		</Screen>
	);
}
