import { Link } from "react-router-dom";
import { CreditCard, Landmark, Wallet, PiggyBank, TrendingUp, Banknote } from "lucide-react";

import { money } from "../lib/format.js";

const ICONS = {
	"Credit Card": CreditCard,
	Savings: Landmark,
	Current: Landmark,
	Cash: Banknote,
	"Prepaid Wallet": Wallet,
	Loan: PiggyBank,
	Investment: TrendingUp,
};

export default function AccountCard({ account }) {
	const Icon = ICONS[account.account_type] || Landmark;
	const balance = Number(account.balance ?? account.cached_balance ?? 0);

	// A liability is held as a negative balance, which is what makes net worth a plain
	// sum. Users think of a card as "I owe 5,200", not "minus 5,200", so flip the label.
	const isDebt = account.is_liability && balance < 0;

	return (
		<Link
			to={`/accounts/${encodeURIComponent(account.name)}`}
			className="flex items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white p-4 shadow-sm transition-transform active:scale-[0.99]"
		>
			<span
				className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-9"
				style={{ background: account.color || undefined }}
			>
				<Icon size={18} />
			</span>
			<div className="min-w-0 flex-1">
				<p className="truncate text-sm font-semibold text-ink-gray-9">{account.account_name}</p>
				<p className="truncate text-xs text-ink-gray-5">{isDebt ? "Outstanding" : account.account_type}</p>
			</div>
			<span className="tnum text-sm font-semibold text-ink-gray-9">
				{money(isDebt ? Math.abs(balance) : balance)}
			</span>
		</Link>
	);
}
