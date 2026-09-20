import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Receipt } from "lucide-react";
import { useFrappeGetDocList } from "frappe-react-sdk";

import TransactionRow from "../components/TransactionRow.jsx";
import { Card, EmptyState, ErrorNote, Screen, Spinner } from "../components/ui.jsx";
import { money, relativeDay } from "../lib/format.js";
import { useCategoryNames } from "../lib/api.js";

const PAGE = 50;

const FILTERS = [
	{ key: "all", label: "All" },
	{ key: "out", label: "Spent" },
	{ key: "in", label: "Received" },
];

export default function Transactions() {
	const [filter, setFilter] = useState("all");
	const [limit, setLimit] = useState(PAGE);
	const categoryNames = useCategoryNames();

	const filters = useMemo(() => {
		const f = [];
		if (filter === "out") f.push(["direction", "=", "Out"]);
		if (filter === "in") f.push(["direction", "=", "In"]);
		return f;
	}, [filter]);

	const { data, error, isLoading } = useFrappeGetDocList("Wallet Transaction", {
		fields: [
			"name",
			"posting_date",
			"description",
			"counterparty",
			"amount",
			"direction",
			"account",
			"category",
		],
		filters,
		orderBy: { field: "posting_date", order: "desc" },
		limit,
	});

	// Group by day so the list reads as a diary rather than an undifferentiated wall.
	const groups = useMemo(() => {
		const out = new Map();
		for (const txn of data || []) {
			const key = txn.posting_date;
			if (!out.has(key)) out.set(key, []);
			out.get(key).push(txn);
		}
		return [...out.entries()];
	}, [data]);

	return (
		<Screen
			title="Activity"
			action={
				// A second way to the same screen as the Add tab. The tab is the one people
				// learn; this one is here because the moment you notice something is missing
				// from the list is the moment you want to add it.
				<Link
					to="/add"
					aria-label="Add transaction"
					className="flex h-10 w-10 items-center justify-center rounded-full"
					style={{ background: "var(--brand)", color: "var(--surface)" }}
				>
					<Plus size={20} />
				</Link>
			}
		>
			<div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
				{FILTERS.map((f) => (
					<button
						key={f.key}
						onClick={() => {
							setFilter(f.key);
							setLimit(PAGE);
						}}
						className="min-h-[36px] shrink-0 rounded-full border px-4 text-sm font-medium transition-colors"
						style={{
							background: filter === f.key ? "var(--brand)" : "var(--surface)",
							color: filter === f.key ? "var(--surface)" : "var(--text-muted)",
							borderColor: filter === f.key ? "var(--brand)" : "var(--border)",
						}}
					>
						{f.label}
					</button>
				))}
			</div>

			{error && <ErrorNote error={error} />}
			{isLoading && !data ? (
				<Spinner />
			) : groups.length === 0 ? (
				<EmptyState
					icon={Receipt}
					title="Nothing here yet"
					hint="Import a bank statement, or add a transaction by hand to get started."
					action={
						<Link
							to="/add"
							className="min-h-[44px] rounded-xl px-4 py-3 text-sm font-semibold"
							style={{ background: "var(--brand)", color: "var(--surface)" }}
						>
							Add a transaction
						</Link>
					}
				/>
			) : (
				<>
					{groups.map(([date, rows]) => {
						const dayTotal = rows.reduce(
							(sum, t) => sum + (t.direction === "In" ? 1 : -1) * Number(t.amount || 0),
							0
						);
						return (
							<section key={date}>
								<div className="flex items-baseline justify-between px-1 pt-2 pb-1">
									<h2 className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
										{relativeDay(date)}
									</h2>
									<span className="tnum text-xs" style={{ color: "var(--text-muted)" }}>
										{money(dayTotal, { compact: true })}
									</span>
								</div>
								<Card className="!py-1">
									{rows.map((txn, i) => (
										<div
											key={txn.name}
											style={{ borderTop: i === 0 ? "none" : "1px solid var(--border)" }}
										>
											<TransactionRow txn={{ ...txn, category_name: categoryNames.get(txn.category) }} />
										</div>
									))}
								</Card>
							</section>
						);
					})}

					{data?.length >= limit && (
						<button
							onClick={() => setLimit((n) => n + PAGE)}
							className="min-h-[44px] w-full rounded-2xl border text-sm font-medium"
							style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
						>
							Load more
						</button>
					)}
				</>
			)}
		</Screen>
	);
}
