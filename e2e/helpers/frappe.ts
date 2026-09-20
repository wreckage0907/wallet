import * as fs from 'node:fs';
import type { APIRequestContext } from '@playwright/test';

/** Where auth.setup.ts parks the CSRF token it lifted out of the desk bootstrap. */
const CSRF_FILE = 'e2e/.auth/csrf.json';

let csrfTokenCache: string | null = null;

/**
 * Frappe rejects an unsafe method without this header, and the token only exists in the
 * page bootstrap — there is no endpoint that hands one out. Read once, reuse.
 */
function csrfToken(): string {
	if (csrfTokenCache !== null) return csrfTokenCache;

	try {
		if (fs.existsSync(CSRF_FILE)) {
			csrfTokenCache = JSON.parse(fs.readFileSync(CSRF_FILE, 'utf-8'))
				.csrf_token as string;
			return csrfTokenCache;
		}
	} catch (error) {
		console.warn('Failed to read CSRF token file:', error);
	}

	csrfTokenCache = '';
	return csrfTokenCache;
}

function writeHeaders(): Record<string, string> {
	const token = csrfToken();
	return {
		'Content-Type': 'application/json',
		...(token ? { 'X-Frappe-CSRF-Token': token } : {}),
	};
}

/** Raw response from a document read — the specs need the status, not just the body. */
export async function getDocResponse(
	request: APIRequestContext,
	doctype: string,
	name: string,
) {
	return request.get(
		`/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
	);
}

export async function getList<T = Record<string, unknown>>(
	request: APIRequestContext,
	doctype: string,
	options: {
		fields?: string[];
		filters?: unknown[];
		limit?: number;
		orderBy?: string;
	} = {},
): Promise<T[]> {
	const params = new URLSearchParams();

	if (options.fields) params.set('fields', JSON.stringify(options.fields));
	if (options.filters) params.set('filters', JSON.stringify(options.filters));
	if (options.orderBy) params.set('order_by', options.orderBy);
	// 0 means "no limit" in Frappe. Without it the REST default of 20 silently truncates,
	// which for an isolation assertion would look exactly like a passing test.
	params.set('limit_page_length', String(options.limit ?? 0));

	const response = await request.get(
		`/api/resource/${encodeURIComponent(doctype)}?${params.toString()}`,
	);

	if (!response.ok()) {
		throw new Error(
			`Failed to list ${doctype}: ${response.status()} ${await response.text()}`,
		);
	}

	return (await response.json()).data as T[];
}

/** Call a whitelisted method. GET, so it works for the app's read endpoints. */
export async function callGet<T = unknown>(
	request: APIRequestContext,
	method: string,
	args: Record<string, string> = {},
): Promise<T> {
	const params = new URLSearchParams(args);
	const response = await request.get(
		`/api/method/${method}?${params.toString()}`,
	);

	if (!response.ok()) {
		throw new Error(
			`Failed to call ${method}: ${response.status()} ${await response.text()}`,
		);
	}

	return (await response.json()).message as T;
}

/** Call a whitelisted method with POST. */
export async function callPost<T = unknown>(
	request: APIRequestContext,
	method: string,
	args: Record<string, unknown> = {},
): Promise<T> {
	const response = await request.post(`/api/method/${method}`, {
		data: args,
		headers: writeHeaders(),
	});

	if (!response.ok()) {
		throw new Error(
			`Failed to call ${method}: ${response.status()} ${await response.text()}`,
		);
	}

	return (await response.json()).message as T;
}

/**
 * Delete a document.
 *
 * Here so a spec that writes can put the site back as it found it. The seeded balances
 * are asserted to the rupee by `dashboard.spec.ts` and `accounts.spec.ts`, and Playwright
 * runs the files in alphabetical order — so a transaction left behind by an earlier spec
 * does not fail its own test, it fails somebody else's, several files later.
 */
export async function deleteDoc(
	request: APIRequestContext,
	doctype: string,
	name: string,
): Promise<void> {
	const response = await request.delete(
		`/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
		{ headers: writeHeaders() },
	);

	if (!response.ok()) {
		throw new Error(
			`Failed to delete ${doctype} ${name}: ${response.status()} ${await response.text()}`,
		);
	}
}
