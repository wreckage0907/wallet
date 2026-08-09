import { Link } from "react-router-dom";
import { ArrowDownLeft, ArrowUpRight, Wallet2 } from "lucide-react";
import { useFrappeGetDocList } from "frappe-react-sdk";

import AccountCard from "../components/AccountCard.jsx";
import TransactionRow from "../components/TransactionRow.jsx";
import { Card, EmptyState, ErrorNote, Screen, Spinner } from "../components/ui.jsx";
import { money, monthRange, relativeDay } from "../lib/format.js";
import { useCashflow, useCategoryNames, useOverview } from "../lib/api.js";

export default function Dashboard() {
	const month = monthRange(0);
	const categoryNames = useCategoryNames();
	const { data, error, isLoading } = useOverview();
	const { data: flow } = useCashflow(month.from, month.to);

	const { data: recent } = useFrappeGetDocList("Wallet Transaction", {
		fields: ["name", "posting_date", "description", "counterparty", "amount", "direction", "category"],
		orderBy: { field: "posting_date", order: "desc" },
		limit: 8,
	});

	const overview = data?.message;
	const cash = flow?.message;

	if (isLoading) return <Spinner />;
	if (error) return <div className="p-4"><ErrorNote error={error} /></div>;

	const accounts = overview?.accounts || [];

	return (
		<Screen title="Wallet">
			<Card className="!p-5">
				<p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
					Net worth
				</p>
				<p className="tnum mt-1 text-3xl font-bold">{money(overview?.net_worth)}</p>
				<div className="mt-4 flex gap-4 text-xs" style={{ color: "var(--text-muted)" }}>
					<span>
						Assets <span className="tnum font-semibold" style={{ color: "var(--text)" }}>{money(overview?.assets, { compact: true })}</span>
					</span>
					{overview?.liabilities > 0 && (
						<span>
							Owed <span className="tnum font-semibold" style={{ color: "var(--text)" }}>{money(overview.liabilities, { compact: true })}</span>
						</span>
					)}
				</div>
				{overview?.has_other_currencies && (
					// Balances in other currencies are deliberately not folded in: converting
					// them would need a rate we do not have, and adding them raw would produce
					// a number that is wrong in every currency.
					<p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
						{overview.currency} accounts only.{" "}
						{overview.by_currency
							.filter((b) => b.currency !== overview.currency)
							.map((b) => `${b.currency} ${b.net_worth.toLocaleString("en-IN")}`)
							.join(", ")}{" "}
						held separately.
					</p>
				)}
			</Card>

			<div className="grid grid-cols-2 gap-3">
				<Card>
					<span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
						<ArrowDownLeft size={14} style={{ color: "var(--color-money-in)" }} /> In · {month.label}
					</span>
					<p className="tnum mt-1 text-lg font-bold">{money(cash?.money_in, { compact: true })}</p>
				</Card>
				<Card>
					<span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
						<ArrowUpRight size={14} style={{ color: "var(--color-money-out)" }} /> Out · {month.label}
					</span>
					<p className="tnum mt-1 text-lg font-bold">{money(cash?.money_out, { compact: true })}</p>
				</Card>
			</div>

			<section className="pt-2">
				<div className="mb-2 flex items-center justify-between">
					<h2 className="text-sm font-semibold">Accounts</h2>
					<Link to="/accounts" className="text-xs font-medium" style={{ color: "var(--brand)" }}>
						See all
					</Link>
				</div>
				{accounts.length === 0 ? (
					<EmptyState
						icon={Wallet2}
						title="No accounts yet"
						hint="Add your bank accounts, then import a statement to fill in the transactions."
					/>
				) : (
					<div className="space-y-2">
						{accounts.slice(0, 4).map((account) => (
							<AccountCard key={account.name} account={account} />
						))}
					</div>
				)}
			</section>

			{recent?.length > 0 && (
				<section className="pt-2">
					<div className="mb-1 flex items-center justify-between">
						<h2 className="text-sm font-semibold">Recent</h2>
						<Link to="/transactions" className="text-xs font-medium" style={{ color: "var(--brand)" }}>
							See all
						</Link>
					</div>
					<Card className="!py-1">
						{recent.map((txn, i) => (
							<div
								key={txn.name}
								style={{ borderTop: i === 0 ? "none" : "1px solid var(--border)" }}
							>
								<TransactionRow txn={{ ...txn, category_name: categoryNames.get(txn.category) || relativeDay(txn.posting_date) }} />
							</div>
						))}
					</Card>
				</section>
			)}
		</Screen>
	);
}
