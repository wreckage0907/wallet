// Thin wrappers over the app's whitelisted methods.
//
// Everything goes through frappe-react-sdk so auth, CSRF and SWR caching are handled
// once. Read endpoints are hooks; writes are plain calls.

import { useMemo } from "react";
import { useFrappeGetCall, useFrappeGetDocList, useFrappePostCall } from "frappe-react-sdk";

export const M = {
	overview: "wallet.api.balance.get_overview",
	accountBalance: "wallet.api.balance.get_account_balance",
	cashflow: "wallet.api.balance.get_cashflow",
	rebuild: "wallet.api.balance.rebuild_balances",
	ensureSetup: "wallet.api.setup.ensure_setup",
	restoreCategories: "wallet.api.setup.restore_default_categories",
	parseStatement: "wallet.api.import_api.parse_statement",
	commitImport: "wallet.api.import_api.commit_import",
	updateMapping: "wallet.api.import_api.update_mapping",
	setRowStatus: "wallet.api.import_api.set_row_status",
	saveAsFormat: "wallet.api.import_api.save_as_format",
	previewLayout: "wallet.api.import_api.preview_layout",
};

export function useOverview(asOn) {
	return useFrappeGetCall(M.overview, asOn ? { as_on: asOn } : undefined, undefined, {
		revalidateOnFocus: true,
	});
}

export function useCashflow(from, to, account) {
	return useFrappeGetCall(
		M.cashflow,
		{ from_date: from, to_date: to, ...(account ? { account } : {}) },
		undefined,
		{ revalidateOnFocus: false }
	);
}

export function useEnsureSetup() {
	return useFrappePostCall(M.ensureSetup);
}

/**
 * docname -> category name.
 *
 * Wallet Category is autonamed `hash`, so a transaction's `category` field is an opaque
 * id. The list is small (about a hundred rows) and changes rarely, so it is fetched once
 * and resolved on the client rather than denormalising a name onto every transaction.
 */
export function useCategoryNames() {
	const { data } = useFrappeGetDocList("Wallet Category", {
		fields: ["name", "category_name", "category_type"],
		limit: 0,
	});

	return useMemo(() => {
		const map = new Map();
		for (const row of data || []) map.set(row.name, row.category_name);
		return map;
	}, [data]);
}
