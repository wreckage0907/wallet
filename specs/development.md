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

## Server tests

```bash
bench --site <site> run-tests --app wallet          # everything
bench --site <site> run-tests --app wallet --module wallet.tests.utils.test_dedup
```

402 tests, covering every Python module in the app. Where a new test file goes, and the
conventions the suites follow, are in [`testing.md`](testing.md) — read that before adding
one.

| Area | Covered by |
|---|---|
| Statement cell parsing, header detection | `wallet/tests/statement/test_parse.py`, `test_detect.py` |
| Reading a file into a grid, decryption | `wallet/tests/statement/test_reader.py`, `test_decrypt.py` |
| Transaction fingerprints | `wallet/tests/utils/test_dedup.py` |
| Categorization rules | `wallet/tests/test_categorization.py` |
| Wallet Settings defaults | `wallet/tests/test_settings.py` |
| Balances, net worth, cashflow | `wallet/tests/api/test_balance.py` |
| The import wizard's endpoints | `wallet/tests/api/test_import_api.py` |
| Owner isolation | `wallet/tests/test_permissions.py` |
| Roles, per-user seeding, `as_user` | `wallet/tests/test_install.py` |
| Setup endpoints, the apps-screen gate | `wallet/tests/api/test_setup.py`, `test_permission.py` |
| `User.after_insert` | `wallet/tests/doc_events/test_user.py` |
| Serving the PWA shell and service worker | `wallet/tests/test_pwa.py`, `wallet/tests/www/test_wallet.py` |
| MCP tools | `wallet/tests/mcp/test_tools.py` |
| Doctype controllers | `test_<doctype>.py` beside each controller |

Statements are built in memory by `wallet/tests/fixtures.py`, never checked in — see the
repo convention below.

Four tests in `test_pwa.py` skip unless `yarn build` has run, because the service worker
they read is build output and build output is gitignored. They report the reason.

## End-to-end tests

```bash
cd apps/wallet
yarn install
npx playwright install chromium

# the fixtures live server-side, so bench seeds them, not the browser
bench --site <site> execute wallet.tests.e2e_seed.seed

BASE_URL=http://<site>:8000 yarn test:e2e       # headless
BASE_URL=http://<site>:8000 yarn test:e2e:ui    # pick and watch individual specs
```

37 specs, split by the surface they exercise:

| Path | Project | What it covers |
|---|---|---|
| `e2e/tests/pwa/` | `pwa` (Pixel 7) | the mobile PWA at `/wallet` |
| `e2e/tests/desk/` | `desk` (Desktop Chrome) | the desk workspace at `/app/wallet` |
| `e2e/tests/api/` | `desk` | owner isolation, straight at `/api/resource` |

**The suite never logs in as Administrator.** `permissions.py` exempts it from owner
isolation, so a session holding it would pass every isolation assertion no matter how
broken the query conditions were. `wallet/tests/e2e_seed.py` seeds two ordinary
`Wallet User` accounts instead — creating a user with a known password is not something
the browser can do for itself, which is why the fixtures go through `bench execute`. The
second holder's data is a canary that must never appear in the first one's session; it
holds the largest balance in the dataset, so a leak would also move every headline figure
the dashboard renders.

**The browser and the site must sit at the same UTC offset.** The seeder writes dates in
site time and the specs read them back through the browser's clock. Frappe takes that
timezone from System Settings, which only the setup wizard ever fills in, so a site that
never ran it falls back to `get_system_timezone()`'s hard-coded `Asia/Kolkata`. If your
machine is elsewhere, export `WALLET_E2E_TZ=<the site's zone>`; `auth.setup.ts` fails with
the exact value to use. CI derives it from the running site.

Fixture amounts and names are declared once in `e2e/helpers/fixtures.ts` and everything
else derives from them, so changing a seeded figure cannot leave a stale expectation
behind in a spec. Money assertions go through the same `Intl` formatting the app uses
rather than hard-coding `₹1,52,750.00` into thirty places.

## CI

Four workflows, all on pull requests:

| Workflow | Job | What it proves |
|---|---|---|
| `ci.yml` | Server Tests | `bench run-tests --app wallet` on a site built from scratch |
| `frontend.yml` | Lint & Build PWA | `oxlint`, `yarn build`, and that the artefacts actually landed |
| `ui-tests.yml` | Playwright E2E Tests | the whole stack, seeded and driven in a browser |
| `linters.yml` | Semantic Commits / Semgrep / Pre-Commit | conventional commits, Frappe's semgrep rules, `pre-commit` |

`ci.yml` and `ui-tests.yml` each build a complete bench on the runner — `bench init`,
`new-site`, `install-app` — because a Frappe app cannot be tested without a database
behind it. There is no mocking layer; doctypes and permissions are rows.

**`bench build` never runs an app's Vite build.** It only runs Frappe's own esbuild over
`*.bundle.*` files (`frappe/build.py`). Since the PWA build output is gitignored, `/wallet`
serves nothing without an explicit `yarn build`, so both `frontend.yml` and `ui-tests.yml`
run one; `frontend.yml` then asserts the output exists rather than trusting the exit code.

**The Playwright job is not sharded.** Every shard would pay for its own `bench init` and
`new-site`, which costs far more than the tests it would save.

Python is pinned to 3.14 to match `requires-python` in `pyproject.toml` — `bench get-app`
runs `pip install -e .`, which refuses anything older. See finding 3 in
[`audit-2026-08-30.md`](audit-2026-08-30.md); if that floor moves, move the workflows with
it.

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
