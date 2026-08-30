/**
 * The PWA's base path, in one place.
 *
 * Kept in sync by hand with the two other definitions of this route — there is no
 * automatic mechanism:
 *   - `basename` passed to the router in frontend/src/main.jsx
 *   - `website_route_rules` in wallet/hooks.py
 */
export const APP_BASE = '/wallet';

/** Build a path inside the PWA: `appUrl('accounts')` -> `/wallet/accounts`. */
export function appUrl(...segments: string[]): string {
	return segments.length ? [APP_BASE, ...segments].join('/') : APP_BASE;
}

/** The desk workspace, where creating and editing still lives. */
export const DESK_WORKSPACE = '/app/wallet';

/** Matches a URL sitting on some account's detail screen — for `toHaveURL`. */
export const ACCOUNT_DETAIL_URL_RE = new RegExp(`${APP_BASE}/accounts/.+`);
