import AmountText from "./AmountText.jsx";

export default function TransactionRow({ txn, showAccount = false }) {
	const title = txn.counterparty || txn.description || "Untitled";
	const meta = [txn.category_name, showAccount ? txn.account_name : null].filter(Boolean);

	return (
		<div className="flex items-start gap-3 py-3">
			<div className="min-w-0 flex-1">
				<p className="truncate text-sm font-medium text-ink-gray-9">{title}</p>
				{meta.length > 0 && (
					<p className="mt-0.5 truncate text-xs text-ink-gray-5">{meta.join(" · ")}</p>
				)}
			</div>
			<AmountText value={txn.amount} direction={txn.direction} className="text-sm" />
		</div>
	);
}
