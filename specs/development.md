# Development

## Frontend

```bash
cd apps/wallet/frontend
yarn install
yarn dev      # Vite on :8080, proxied to the bench
yarn build    # → wallet/public/frontend/ and wallet/www/wallet.html
```

Build output is **gitignored**, so a fresh clone always needs `yarn build`. Skipping it
gets a 404 for the PWA and for the app icon on the `/apps` screen.

## Backend

```bash
bench --site <site> run-tests --app wallet
```

29 tests, all covering the MCP tools. See finding 4 in
[`audit-2026-08-30.md`](audit-2026-08-30.md) for what is not covered.

## Pre-commit

```bash
cd apps/wallet
pre-commit install
```

Runs `ruff`, `eslint`, `prettier` and `pyupgrade`.

## Repo conventions

**Never commit a bank statement.** `.gitignore` blocks `*.xlsx`, `*.xls`, `*.xlsm`,
`*.csv` and `*.pdf` at the repo root. Real statements are the natural test fixture and the
easiest thing in the world to add by accident.

**Whitelisted methods need full type annotations.** `hooks.py` sets
`require_type_annotated_api_methods = True`, so an unannotated parameter raises
`FrappeTypeError` at call time. Optional parameters must be written `str | None = None`,
never a bare `str = None`, because values are coerced through pydantic. Structured
arguments must be `dict | str` / `list[dict] | str` and normalised with
`frappe.parse_json`, because a form-encoded POST from the browser delivers them as a JSON
*string*.

**Read Wallet Settings through `wallet.settings.get_setting`.**
`frappe.db.get_single_value` returns `0` for a Single that has never been saved, so reading
`auto_categorize` directly reports "disabled" on a fresh site even though the field is
declared with a default of 1.

## Environment

The development site runs under Frappe Manager in Docker (`fm__demo_localhost__*`),
reachable at `http://demo.localhost` through `fm_global-nginx-proxy`. The desk is served at
`/desk`, not `/app` — `/app` redirects.

Note that `site_config.json` records `admin_password: admin`, but that pair no longer
works; the login returns 401.
