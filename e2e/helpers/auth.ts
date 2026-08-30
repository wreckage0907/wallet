import type { APIRequestContext, Page } from '@playwright/test';
import { E2E_PASSWORD, E2E_USER } from './fixtures';

/**
 * Log in over the Frappe API. Faster than the UI form and, more importantly, it does not
 * depend on the login page's markup, which is Frappe's and not ours to keep stable.
 */
export async function loginViaAPI(
	request: APIRequestContext,
	email = E2E_USER,
	password = E2E_PASSWORD,
): Promise<void> {
	const response = await request.post('/api/method/login', {
		form: { usr: email, pwd: password },
	});

	if (!response.ok()) {
		throw new Error(
			`Login failed for ${email}: ${response.status()} ${await response.text()}`,
		);
	}
}

/** Who the current session belongs to — 'Guest' when it belongs to nobody. */
export async function loggedInUser(
	request: APIRequestContext,
): Promise<string> {
	const response = await request.get(
		'/api/method/frappe.auth.get_logged_user',
	);
	if (!response.ok()) return 'Guest';

	const data = await response.json();
	return data.message || 'Guest';
}

export async function logout(page: Page): Promise<void> {
	await page.goto('/api/method/logout');
}
