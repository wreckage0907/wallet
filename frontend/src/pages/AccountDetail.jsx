import { useParams, Link } from "react-router-dom";
import { ChevronLeft, Receipt } from "lucide-react";
import { useFrappeGetDoc, useFrappeGetDocList } from "frappe-react-sdk";

import TransactionRow from "../components/TransactionRow.jsx";
import { Card, EmptyState, ErrorNote, Spinner } from "../components/ui.jsx";
import { money, monthRange, relativeDay } from "../lib/format.js";
import { useCashflow, useCategoryNames } from "../lib/api.js";

export default function AccountDetail() {
	const { name } = useParams();
	const month = monthRange(0);
	const categoryNames = useCategoryNames();

	const { data: account, error, isLoading } = useFrappeGetDoc("Wallet Account", name);
	const { data: flow } = useCashflow(month.from, month.to, name);
	const { data: txns } = useFrappeGetDocList("Wallet Transaction", {
		fields: ["name", "posting_date", "description", "counterparty", "amount", "direction", "category"],
		filters: [["account", "=", name]],
		orderBy: { field: "posting_date", order: "desc" },
		limit: 50,
	});

	if (isLoading) return <Spinner />;
	if (error) return <div className="p-4"><ErrorNote error={error} /></div>;

	const balance = Number(account?.cached_balance || 0);
	const isDebt = account?.is_liability && balance < 0;
	const cash = flow?.message;

	return (
		<>
			<header className="safe-top sticky top-0 z-40 flex items-center gap-2 px-2 pt-3 pb-2 backdrop-blur"
				style={{ background: "color-mix(in srgb, var(--surface-sunken) 88%, transparent)" }}>
				<Link
					to="/accounts"
					className="flex h-10 w-10 items-center justify-center rounded-full"
					style={{ color: "var(--text-muted)" }}
					aria-label="Back to accounts"
				>
					<ChevronLeft size={22} />
				</Link>
				<h1 className="truncate text-lg font-bold">{account?.account_name}</h1>
			</header>

			<div className="space-y-3 px-4">
				<Card className="!p-5">
					<p className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
						{isDebt ? "Outstanding" : "Balance"}
					</p>
					<p className="tnum mt-1 text-3xl font-bold">
						{money(isDebt ? Math.abs(balance) : balance)}
					</p>
					<div className="mt-4 flex gap-4 text-xs" style={{ color: "var(--text-muted)" }}>
						<span>
							In {month.label}{" "}
							<span className="tnum font-semibold" style={{ color: "var(--color-money-in)" }}>
								{money(cash?.money_in, { compact: true })}
							</span>
						</span>
						<span>
							Out{" "}
							<span className="tnum font-semibold" style={{ color: "var(--color-money-out)" }}>
								{money(cash?.money_out, { compact: true })}
							</span>
						</span>
					</div>
				</Card>

				{txns?.length ? (
					<Card className="!py-1">
						{txns.map((txn, i) => (
							<div key={txn.name} style={{ borderTop: i === 0 ? "none" : "1px solid var(--border)" }}>
								<TransactionRow txn={{ ...txn, category_name: categoryNames.get(txn.category) || relativeDay(txn.posting_date) }} />
							</div>
						))}
					</Card>
				) : (
					<EmptyState
						icon={Receipt}
						title="No transactions"
						hint="Import a statement for this account to fill it in."
					/>
				)}
			</div>
		</>
	);
}
