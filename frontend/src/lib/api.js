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
	createTransaction: "wallet.api.transaction_api.create_transaction",
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

/**
 * The accounts a transaction can be filed against.
 *
 * Disabled accounts are left out: a closed account is not somewhere new money moves, and
 * `get_overview` already hides them, so offering one here would let a person file spend
 * the dashboard then refuses to show.
 */
export function useAccountOptions() {
	return useFrappeGetDocList("Wallet Account", {
		fields: ["name", "account_name", "account_type", "currency", "is_liability"],
		filters: [["disabled", "=", 0]],
		orderBy: { field: "account_name", order: "asc" },
		limit: 0,
	});
}

/**
 * Categories to offer on the Add screen.
 *
 * Deliberately a different query from `useCategoryNames`: that one resolves the category
 * on an *existing* transaction and so must include disabled ones, or a row filed under a
 * since-retired category would render with no label at all.
 */
export function useCategoryOptions() {
	return useFrappeGetDocList("Wallet Category", {
		fields: ["name", "category_name", "category_type"],
		filters: [["disabled", "=", 0]],
		orderBy: { field: "category_name", order: "asc" },
		limit: 0,
	});
}

export function useCreateTransaction() {
	return useFrappePostCall(M.createTransaction);
}

function stripTags(value) {
	// Frappe messages carry markup — <b>, and a <br> between the sentence and its detail.
	return String(value || "")
		.replace(/<br\s*\/?>/gi, " ")
		.replace(/<[^>]*>/g, "")
		.replace(/\s+/g, " ")
		.trim();
}

/**
 * The sentence a person should read, out of a Frappe error.
 *
 * `frappe.throw` puts it in `_server_messages` — a JSON array of JSON strings — and
 * leaves `message` holding a generic fallback and `exception` the Python class name.
 * Showing either of those gets "ValidationError" on screen, when the server went to the
 * trouble of saying "5 Aug 2026 is before this account's opening date".
 */
export function serverMessage(error, fallback = "Something went wrong.") {
	if (!error) return fallback;

	let entries = [];
	try {
		entries = JSON.parse(error._server_messages || "[]");
	} catch {
		entries = [];
	}

	for (const entry of entries) {
		let parsed = entry;
		try {
			parsed = JSON.parse(entry);
		} catch {
			// Not every entry is a JSON object; a bare string is also valid here.
		}
		const text = stripTags(parsed?.message ?? parsed);
		if (text) return text;
	}

	// `exception` reads "frappe.exceptions.ValidationError: Amount must be…" — the
	// sentence is in there, behind a class name nobody outside this repo can parse.
	const exception = stripTags(error.exception).replace(/^[\w.]*Error:\s*/, "");
	return exception || stripTags(error.message) || fallback;
}
