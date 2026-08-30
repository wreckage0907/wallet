### Wallet

Personal Finance Management

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app wallet
```

### MCP server

Wallet can act as an [MCP](https://modelcontextprotocol.io) server, so an AI agent can read
your accounts and transactions and record new ones.

```
/api/method/wallet.mcp.handle_mcp
```

| Tool | |
|---|---|
| `list_accounts` | balances, including what is owed on a credit card |
| `list_transactions` | filter by account, date, category, direction, or free text |
| `list_categories` | the names the other tools accept |
| `get_spending_summary` | money in, money out and spend per category over a period |
| `add_transaction` | record one transaction |

One endpoint rather than separate read and write URLs. Splitting them looks like a
boundary and is not one: a Frappe OAuth bearer token is session-wide, so a token issued for
a "read-only" URL can post to the write URL just as easily. Instead, **writes are off by
default** and enabled with `Allow MCP Writes` in Wallet Settings — checked inside the tool,
so it holds however the endpoint is reached. That setting is a site-wide Single, not a
per-user opt-in: on a multi-user site, turning it on opens the write path for every
connected agent, each still confined to its own owner's records. Which tools an agent should reach for is
expressed with MCP's own `readOnlyHint` / `destructiveHint` annotations, which clients use
to gate and confirm.

#### Setup

`frappe-mcp` is not in `pyproject.toml`: it pins `Werkzeug==3.1.3` and `pydantic~=2.11.7`,
while Frappe pins newer versions of both, so a normal resolve would downgrade Werkzeug and
break the bench. Install it without its dependencies instead:

```bash
./env/bin/pip install jsonschema
./env/bin/pip install --no-deps \
	git+https://github.com/frappe/mcp.git@11d5076b1bf4483b2ff6751a13e0736f5396b1e6
bench restart
```

The commit is pinned deliberately — the library ships breaking changes without notice.

This install lives only in the bench virtualenv, and nothing in the repo restores it. A
container or image rebuild, a fresh `bench init`, or a Frappe Cloud deploy will not have
it, and the endpoint will fail with `Failed to get method for command
wallet.mcp.handle_mcp with No module named 'frappe_mcp'`. Re-run the two commands above.
The rest of the app is unaffected — nothing else imports `frappe_mcp`.

Requires a Frappe version with the OAuth2 metadata endpoints
([frappe#33188](https://github.com/frappe/frappe/pull/33188)) — v16 or later. Nothing else
needs configuring: `OAuth Settings` enables dynamic client registration and the
`.well-known` metadata endpoints by default.

Verify by listing the tools (as a user with the `Wallet User` or `System Manager` role —
`wallet/install.py` creates the role but does not assign it):

```bash
curl -s -X POST -H "Authorization: token <api_key>:<api_secret>" \
	-H "Content-Type: application/json" \
	-d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
	https://<your-site>/api/method/wallet.mcp.handle_mcp
```

Note that `frappe-mcp check` reports this handler as "not properly registered". That is
expected: it looks for the `@mcp.register()` decorator, which this app deliberately does
not use — see `wallet/mcp/__init__.py`.

#### Connecting a client

There is no API key to copy. Paste the endpoint URL into your MCP client; it registers
itself, opens your normal Frappe login, and receives a token once you approve.

```bash
claude mcp add --transport http wallet \
	https://<your-site>/api/method/wallet.mcp.handle_mcp
```

> [!WARNING]
> Dynamic client registration requires **every** `redirect_uri` to be `https`, unless the
> site runs with `developer_mode` on (`frappe/integrations/utils.py`). There is no loopback
> exemption. MCP clients register loopback redirects like `http://localhost:<port>/callback`,
> so on a production site the self-registration flow above fails with `redirect_uris must
> be https`. Either register an OAuth Client for the client by hand, or keep
> `developer_mode` on. This is a `developer_mode` distinction, not a local-versus-remote one.

Browser-based clients such as the MCP Inspector additionally need their origin listed in
`OAuth Settings → Allowed Public Client Origins`, which is empty by default. Native clients
(Claude Code, Claude Desktop) do not.

> [!IMPORTANT]
> A Frappe OAuth bearer token is session-wide, not endpoint-scoped — `validate_oauth`
> derives a token's required scopes from the token itself. A token issued for Wallet can
> reach any whitelisted method on the site as you. `Allow MCP Writes` closes the Wallet
> write path specifically; it does not contain a client you do not trust.
>
> Connecting as **Administrator** bypasses the owner-based isolation the tools rely on
> (`wallet/permissions.py` exempts it deliberately), so every answer would silently
> aggregate all users' data. Connect as your own user.

### Tests

**Server tests** — `bench --site <site> run-tests --app wallet`. Currently the MCP tool
bodies (`wallet/tests/test_mcp_tools.py`).

**End-to-end tests** — Playwright, against a running bench.

```bash
# once
yarn install
npx playwright install chromium

# the fixtures live server-side, so they are seeded by bench, not by the browser
bench --site <site> execute wallet.tests.e2e_seed.seed

BASE_URL=http://<site>:8000 yarn test:e2e          # headless
BASE_URL=http://<site>:8000 yarn test:e2e:ui       # pick and watch individual specs
```

The browser and the site have to sit at the same UTC offset — the seeder writes dates in
site time and the specs read them back through the browser's clock. Frappe takes that
timezone from System Settings, which only the setup wizard ever fills in, so a site that
never ran it falls back to `Asia/Kolkata`. If your machine is elsewhere, export
`WALLET_E2E_TZ=<the site's zone>`; `auth.setup.ts` fails with the exact value to use. CI
derives it from the running site.

The suite never logs in as Administrator. `wallet/permissions.py` exempts Administrator
from owner isolation, so a session holding it would pass every isolation assertion no
matter how broken the query conditions were. `wallet/tests/e2e_seed.py` therefore creates
two ordinary `Wallet User` accounts — the one the browser drives, and a second holder
whose data acts as a canary that must never appear in the first one's session. Both are
idempotent to re-seed.

Specs are split by the surface they exercise:

| Path | Project | What it covers |
|---|---|---|
| `e2e/tests/pwa/` | `pwa` (Pixel 7) | the mobile PWA at `/wallet` |
| `e2e/tests/desk/` | `desk` (Desktop Chrome) | the desk workspace at `/app/wallet` |
| `e2e/tests/api/` | `desk` | owner isolation, straight at `/api/resource` |

Amounts and fixture names are declared once in `e2e/helpers/fixtures.ts` and derived from
there, so changing a seeded figure does not leave a stale expectation in a spec.

### CI

Four workflows, all on pull requests:

| Workflow | Job | What it proves |
|---|---|---|
| `ci.yml` | Server Tests | `bench run-tests --app wallet` on a fresh site |
| `frontend.yml` | Lint & Build PWA | `oxlint`, `yarn build`, and that the build artefacts actually exist |
| `ui-tests.yml` | Playwright E2E Tests | the whole stack, seeded and driven in a browser |
| `linters.yml` | Semantic Commits / Semgrep / Pre-Commit | conventional commits, Frappe's semgrep rules, `pre-commit` |

`bench build` runs only Frappe's own esbuild over `*.bundle.*` files — it never runs an
app's Vite build. The PWA build output is gitignored, so both `frontend.yml` and
`ui-tests.yml` run `yarn build` explicitly; without it `/wallet` serves nothing.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/wallet
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
