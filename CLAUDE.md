# CLAUDE.md

## About

**Wallet** is a Frappe v16 app for personal finance: you add your bank accounts, import
the statement files your bank emails you, and the app parses, de-duplicates and
auto-categorizes every row into `Wallet Transaction` records. It ships a mobile-first PWA
at `/wallet`, a Frappe desk workspace for the heavier forms, and an MCP server so an AI
agent can read your accounts and record transactions.

Single-user-per-dataset by design: every personal record is isolated to its `owner`, so
one site can host many people without their money ever mixing.

Written for Indian retail banking — dd/mm dates, `Dr`/`Cr` suffixes, running-balance
columns, ECMA-376 password-protected xlsx, INR defaults, and seed categorization rules
for Swiggy / Zomato / UPI / FASTag / NACH-EMI narrations.

- **App name:** `wallet` · **Module:** `Wallet` · **Version:** `0.0.1` · **License:** MIT
- **Routes:** `/wallet` (PWA), `/app/wallet` (desk workspace),
  `/api/method/wallet.mcp.handle_mcp` (MCP)

## Layout

```
wallet/
  hooks.py                  app wiring: routes, permissions, PWA renderer, scheduler
  permissions.py            owner-based isolation (READ THIS FIRST)
  install.py                roles + per-user seeding of categories & rules
  settings.py               Wallet Settings reads that respect declared defaults
  categorization.py         pure rule-matching over plain dicts
  pwa.py                    serves the service worker from the site root
  api/
    balance.py              balance / net-worth / cashflow aggregates
    import_api.py           whitelisted endpoints for the import wizard
    setup.py                lazy per-user seeding on PWA boot
    permission.py           apps-screen gate
  statement/
    decrypt.py              ECMA-376 (OLE2) decryption via msoffcrypto-tool
    reader.py               file -> list[list[cell]]  (xlsx / xls / csv)
    detect.py               header-row detection + column -> field mapping
    parse.py                cell -> date / signed amount
  utils/dedup.py            content-derived transaction fingerprints
  mcp/                      MCP endpoint, tool bodies, name resolution, rollback guard
  wallet/doctype/           10 doctypes (see below)
  tests/test_mcp_tools.py   29 tests, MCP tools only
frontend/                   React 19 + Vite 8 + Tailwind 4 PWA, built into wallet/public/
```

## Data model

| DocType | Kind | Owner-isolated | Notes |
|---|---|---|---|
| `Wallet Account` | normal, `autoname: hash` | yes | name unique **per user**; `is_liability` derived from type; `cached_balance` is a display cache only |
| `Wallet Transaction` | normal, `TXN-.YYYY.-.#####` | yes | the ledger; `signed_amount` and `dedup_hash` are derived |
| `Wallet Category` | **NestedSet tree**, `autoname: hash` | yes | Expense / Income / Transfer; tree so a parent rolls up its children in one range query |
| `Wallet Categorization Rule` | normal | yes | Contains / Starts With / Equals / Regex, with priority |
| `Wallet Statement Import` | `IMP-.YYYY.-.#####` | yes | the import wizard document |
| `Wallet Statement Import Row` | child table | (parent) | staged rows, editable before commit |
| `Wallet Statement Format` | normal | no — shared | remembered column mapping, keyed by header signature |
| `Wallet Statement Column Mapping` | child table | (parent) | one target field -> column index |
| `Wallet Bank` | normal, `field:bank_name` | no — shared reference | |
| `Wallet Settings` | **Single** | n/a | System Manager only; holds `allow_mcp_writes` |

`Wallet Account` and `Wallet Category` are `autoname: hash` deliberately, so two users can
each own a "HDFC Savings" and a "Groceries". The cost is that their docnames are opaque
ids — which is why `wallet/mcp/resolve.py` and `frontend/src/lib/api.js` both exist to map
human names back to docnames.

## Invariants — do not break these

**1. Isolation is `owner`, and `frappe.get_all` bypasses it.**
There is no `user` Link field; the framework's `owner` column is the only scope. It is
enforced in three places (`if_owner=1` in doctype perms, `permission_query_conditions`,
`has_permission`) — all in `wallet/permissions.py`. Only `Administrator` is exempt;
`System Manager` deliberately is **not**, because the account holder usually has that role
and exempting it would mix other people's transactions into their own list views.
`frappe.get_all` and `frappe.qb` skip permission query conditions entirely. Use
`frappe.get_list`, or pass an explicit `owner` filter. **Grep for `get_all` in review.**

**2. Balance is an aggregate, never a stored counter.**
`balance(account, as_on) = opening_balance + SUM(signed_amount) where posting_date <= as_on`.
A stored counter drifts — edits need before/after diffs, bulk SQL skips hooks, a dying
worker leaves a partial delta. `Wallet Account.cached_balance` exists only so an account
list renders in one query; its worst failure mode is staleness, and the nightly
`rebuild_all_balances` plus the Settings button are its repair paths.

**3. Sign convention.** `amount` is always positive; `direction` (In/Out) carries the sign
into `signed_amount`. Money owed on a credit card is a negative balance, so net worth is a
plain sum and `is_liability` only flips the UI label.

**4. Dedup hashes are stamped once, on insert, and never recomputed.**
Three tiers, in `wallet/utils/dedup.py`: reference number → running balance discriminator
→ occurrence ordinal. Recomputing on save would re-derive an ordinal that now collides
with a sibling row.

**5. Currencies are never summed across.** Totals are kept per currency; the dashboard and
`list_accounts` say so via `has_other_currencies` rather than implying a wrong total.

**6. Bulk imports set `frappe.flags.wallet_bulk_import`.** Without it every inserted row
triggers a full account SUM and a 5,000-row import goes quadratic. Always reset it in a
`finally`.

**7. Whitelisted methods need full type annotations.**
`hooks.py` sets `require_type_annotated_api_methods = True`. Optional params must be
`str | None = None`, never `str = None`. Structured args must be `dict | str` /
`list[dict] | str` and run through `frappe.parse_json`, because a form-encoded POST
delivers them as a JSON string.

**8. Read Wallet Settings through `wallet.settings.get_setting`.**
`frappe.db.get_single_value` returns `0` for a Single that has never been saved, so
`auto_categorize` would silently read as disabled on a fresh site. `get_setting` falls back
to the DocField's declared default.

## Statement import pipeline

`file → decrypt → read_grid → detect_header → stage rows (child table) → preview/edit → commit_rows → reconcile`

- Staging lives in a real child table, not a JSON blob, precisely so the preview is
  *editable* — fix a category, skip a row — before anything is written.
- Layout resolution order: explicitly chosen format → format remembered by
  `header_signature` (this is what makes a repeat import one click) → heuristic detection.
- Footer/summary rows are recognised **after** failing to parse as a transaction, never
  before: a generic "total" marker once silently dropped real payments to "TotalEnergies".
- dd/mm vs mm/dd is decided **per column**, not per cell, by looking for any first
  component > 12.
- Each row commits inside its own savepoint, so one bad row cannot abort the batch.
- `reconcile()` compares the computed closing balance against the statement's own stated
  closing balance. That single variance number checks parsing, sign convention and dedup
  all at once.

## MCP server

One endpoint (`wallet.mcp.handle_mcp`), five tools: `list_accounts`, `list_transactions`,
`list_categories`, `get_spending_summary`, `add_transaction`.

- Reads and writes share one URL on purpose. A Frappe OAuth bearer token is session-wide,
  so a "read-only URL" is not a boundary. Writes are off by default and gated by
  `Wallet Settings.allow_mcp_writes`, checked **inside the tool body**.
- `@mcp.register()` is deliberately not used — it makes Frappe resolve the owning app as
  `frappe_mcp` and every request dies. `mcp.handle()` is used instead. `frappe-mcp check`
  reporting "not properly registered" is expected and cosmetic.
- Every tool is wrapped in `wallet.mcp.guard.guarded`, including the read ones:
  `frappe_mcp` swallows exceptions into `isError: true` over HTTP 200, so Frappe would
  otherwise commit partial state. "All tools go through the guard" is checkable by
  looking; "the write tools do" has to be remembered.
- Tool **docstrings are the API contract** — `frappe-mcp` derives the tool and argument
  descriptions from them. The sign convention especially has to be spelled out.
- Disabled accounts and categories are hidden from listing *and* from name resolution, so
  the model can never filter by a name it was never shown.
- `frappe-mcp` is **not** in `pyproject.toml` (it would downgrade Werkzeug and break the
  bench) — install with `--no-deps`; see README.

## Frontend

React 19 + Vite 8 + Tailwind 4 + `frappe-react-sdk`, mounted at `/wallet` with
`basename="/wallet"`. Five screens: Dashboard, Accounts, Account Detail, Transactions,
More. It is currently **read-only** — creating and editing happens in the desk at
`/app/wallet`.

The service worker is served from the *site root* by `wallet/pwa.py`, not from `/assets/`.
A worker only controls URLs at or below its own directory, and Frappe's `StaticPage`
refuses to serve `.js`/`.json` from `www/`. Filename is `wallet_sw.js` with no slash, so
the `/wallet/<path>` route rule does not swallow it.

Build output (`wallet/public/frontend/`, `wallet/www/wallet.html`) is **gitignored** — a
fresh clone must run `cd frontend && yarn install && yarn build` or the PWA and the app
icon 404.

## Audit findings — open

1. **`Wallet Budget` does not exist.** It is listed in `permissions.py:OWNED_DOCTYPES` and
   therefore registered in both `permission_query_conditions` and `has_permission` in
   `hooks.py`. Harmless today (the hooks never fire) but it is a dangling promise: either
   build the doctype or drop the two references.
2. **`requires-python = ">=3.14"` in `pyproject.toml`, but the bench runs Python 3.12.**
   A plain `pip install -e .` would refuse. Loosen it or state the real floor.
3. **Test coverage is MCP-only.** 29 tests, all in `wallet/tests/test_mcp_tools.py`. The
   highest-risk code in the app — `statement/parse.py`, `statement/detect.py`,
   `utils/dedup.py`, `api/balance.py` — has no tests at all. `parse.py` and `detect.py`
   are pure functions over plain data and are the cheapest possible things to cover.
4. **The MCP install is not reproducible.** `frappe-mcp` lives only in the bench
   virtualenv; a container rebuild, fresh `bench init` or Frappe Cloud deploy loses it and
   the endpoint 500s. Documented in the README, but nothing in the repo restores it.
5. **`allow_mcp_writes` is a site-wide Single, not a per-user opt-in.** On a multi-user
   site, one System Manager turning it on opens the write path for every connected agent
   (each still confined to its own owner's records).
6. **No write path in the PWA.** Adding a transaction on a phone means falling back to the
   desk UI, which is the one context the desk is worst at.

## Planning / Spec-ing

Use tracer bullets (from *The Pragmatic Programmer*). When building systems, write code
that gets you feedback as quickly as possible. Tracer bullets are small slices of
functionality that go through all layers of the system, letting you test and validate the
approach early. This surfaces problems and confirms the architecture is sound before
significant time goes into development.

## Testing

Use the `agent-browser` skill to test the feature e2e.

- Site: `http://demo.localhost` (Frappe Manager / Docker, `fm__demo_localhost__*`)
- Credentials: `Administrator` / `admin`
- Python tests: `bench --site demo.localhost run-tests --app wallet`
- Frontend dev server: `cd frontend && yarn dev` (port 8080, proxies to the bench)

> Note for e2e: connecting or testing as **Administrator** bypasses the owner isolation
> everything else relies on (`permissions.py` exempts it). To exercise isolation, use a
> real user.
