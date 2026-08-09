import { Wallet2 } from "lucide-react";

import AccountCard from "../components/AccountCard.jsx";
import { EmptyState, ErrorNote, Screen, Spinner } from "../components/ui.jsx";
import { money } from "../lib/format.js";
import { useOverview } from "../lib/api.js";

export default function Accounts() {
	const { data, error, isLoading } = useOverview();

	if (isLoading) return <Spinner />;
	if (error) return <div className="p-4"><ErrorNote error={error} /></div>;

	const overview = data?.message;
	const accounts = overview?.accounts || [];

	return (
		<Screen title="Accounts">
			{accounts.length === 0 ? (
				<EmptyState
					icon={Wallet2}
					title="No accounts yet"
					hint="Create one in the desk app under Wallet › Wallet Account, then import a statement."
				/>
			) : (
				<>
					<div className="space-y-2">
						{accounts.map((account) => (
							<AccountCard key={account.name} account={account} />
						))}
					</div>
					<div
						className="flex items-center justify-between px-1 pt-3 text-sm"
						style={{ color: "var(--text-muted)" }}
					>
						<span>Combined</span>
						<span className="tnum font-semibold" style={{ color: "var(--text)" }}>
							{money(overview?.net_worth)}
						</span>
					</div>
				</>
			)}
		</Screen>
	);
}
