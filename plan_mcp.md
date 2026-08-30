# Plan: MCP server for Wallet

Status: proposal, not yet implemented. Branch `feat/mcp-server`.

Lets a user connect their Wallet account to an AI agent (Claude, or any MCP client) and
ask about their accounts, transactions and categories — and add a transaction by talking
to it. Phase 1 is deliberately small; everything here is meant to be built on.

---

## 1. Decision: `frappe-mcp`, in-app

Wallet becomes the MCP server itself, over Streamable HTTP, using the official
[`frappe/mcp`](https://github.com/frappe/mcp) library.

The alternative — a standalone FastMCP process talking to Frappe over REST with an API
key — was rejected. It means a second process to run, a second auth model to design, and
a permission story rebuilt outside the framework that already implements it. In-app, the
OAuth bearer token resolves to a real `frappe.session.user` before our code runs, so the
owner-based isolation in `wallet/permissions.py` applies to every tool for free. That is
the whole argument: **the MCP server inherits the app's existing security model instead
of paralleling it.**

The official `mcp` Python SDK (2.0) is async/ASGI-only and cannot be hosted inside
Frappe's WSGI request cycle. `frappe-mcp` exists specifically because of that gap.

Generic third-party Frappe MCP servers were also rejected — they expose doctype CRUD
across the whole site, which is the opposite of what a finance app wants.

---

## 2. Architecture: one endpoint

`/api/method/wallet.mcp.handle_mcp`, carrying all five tools.

This started as two endpoints, read and write. That was wrong, and testing is what showed
it: a Frappe OAuth bearer token is session-wide, so a token issued for the "read-only" URL
can POST to the write URL unchanged. The split looked like a boundary while providing none
of one, which is worse than not having it.

Read-only is only a guarantee if it is enforced where the caller cannot route around it, so
`add_transaction` checks `Wallet Settings.allow_mcp_writes` in the tool body. Off by
default: reading your finances is far less consequential than writing to them. Tool
selection is expressed the way MCP intends, with `readOnlyHint` / `destructiveHint`
annotations that clients gate on.

---

## 3. Auth: OAuth 2.1, no credentials handed to the agent

There is nothing for the user to copy-paste. No API key, no password.

This bench runs **Frappe 17.0.0-dev**, which already has the OAuth work from
[frappe#33188](https://github.com/frappe/frappe/pull/33188). Verified present in
`apps/frappe/frappe/integrations/oauth2.py`:

- `/.well-known/oauth-authorization-server` (RFC 8414)
- `/.well-known/oauth-protected-resource` (RFC 9728)
- Dynamic client registration (RFC 7591) at `frappe.integrations.oauth2.register_client`
- PKCE, `code_challenge_methods_supported: ["S256"]`

`OAuth Settings` ships with `enable_dynamic_client_registration`,
`show_auth_server_metadata` and `show_protected_resource_metadata` all defaulting to `1`,
so no setup doctype work is needed — only verification (§10).

**Connection flow:**

1. User pastes the endpoint URL into their MCP client.
2. Client fetches `.well-known`, discovers the auth server, registers itself dynamically.
3. Browser opens the normal Frappe login; user logs in and approves.
4. Client receives a bearer token.
5. On each call, `frappe/auth.py:654 validate_oauth` resolves the token and calls
   `frappe.set_user(user)`. Tools run as that user.

**Trust boundary, to be stated plainly in the README.** A Frappe OAuth bearer token is
session-wide, not endpoint-scoped: `validate_oauth` derives `required_scopes` from the
token itself, so scope checking is tautological. A token issued for the read-only wallet
endpoint can still call any whitelisted method on the site as that user. The read/write
split is an ergonomic and blast-radius boundary against a *well-behaved* client, not a
sandbox against a hostile one. Do not describe it as one.

---

## 4. Install

`frappe-mcp` pins `Werkzeug==3.1.3` and `pydantic~=2.11.7`. This bench has Werkzeug
**3.1.6** and pydantic **2.12.5**, both pinned exactly by Frappe 17. A plain
`pip install frappe-mcp` downgrades Werkzeug out from under Frappe.

PyPI also only carries `0.1.0` (Jul 2025); the repo's `main` is current — May 2026 added
prompt support and relaxed the click pin. Install from git.

```bash
# inside the Docker bench container
./env/bin/pip install jsonschema
./env/bin/pip install --no-deps git+https://github.com/frappe/mcp.git
```

`--no-deps` is safe: the only transitive dep actually missing is `jsonschema`. click
(8.2.1) and pydantic are already present, and the library uses only `BaseModel` /
`ValidationError` and Werkzeug's `Request` / `Response`, all stable across those versions.

**Do not add `frappe-mcp` to `wallet/pyproject.toml` dependencies** until upstream
relaxes the pins — `bench setup requirements` would resolve it and break the bench.
Document the manual step in the README instead, with a TODO to move it into
`pyproject.toml` once the pins allow.

No `hooks.py` changes are required.

**Correction, found in testing.** This plan originally said `@mcp.register()` would work
because its wrapper takes no arguments. That was the wrong concern. `register` builds its
wrapper inside `frappe_mcp.server.server`, and
`frappe.utils.typing_validations.validate_argument_types` derives the owning app from
`func.__module__.split(".")[0]`. That resolves to `frappe_mcp`, Frappe then tries to
import `frappe_mcp.hooks`, and **every request fails** with
`ModuleNotFoundError: No module named 'frappe_mcp.hooks'`.

The endpoints therefore call `mcp.handle(request, response)` from a function defined in
our own module — the library's documented entry point for mounting on any Werkzeug app.
Returning a `werkzeug.Response` from a whitelisted method is supported by
`frappe.handler.handle`. See `wallet/mcp/endpoint.py`.

---

## 5. Tool surface

Five tools total. Every tool returns a **dict** at the top level — `frappe_mcp` only
populates `structuredContent` when the return value is a dict, so lists get wrapped.

Docstrings are the API contract: Google-style, because `frappe-mcp` derives both the
tool description and the per-argument JSON Schema descriptions from them. The sign
convention in particular has to be spelled out or the model will pass a negative amount
and trip `validate_amount`.

### Read tools — `readOnlyHint: true`

**`list_accounts()`**
Every account with its live balance. Wraps `wallet.api.balance.get_overview`, which
already computes this in two queries.
Returns `{"accounts": [{id, name, type, bank, masked_number, currency, balance,
is_liability}], "net_worth", "assets", "liabilities", "currency"}`.
Covers the "what's on my credit card" question — a credit card is just an account with
`account_type == "Credit Card"` and `is_liability`.

**`list_transactions(account=None, from_date=None, to_date=None, category=None, direction=None, search=None, limit=50)`**
Filtered transaction history, newest first. `account` and `category` take **names**, not
ids (§7). `search` matches description and counterparty. `limit` caps at 200.
Returns `{"transactions": [{id, posting_date, direction, amount, currency, description,
counterparty, category, account}], "count"}`.

**`list_categories()`**
The id↔name map. Not optional: `Wallet Category` is `autoname: hash`, so this is how the
model learns what it may pass to `category` anywhere else.
Returns `{"categories": [{id, name, type, parent}]}`.

**`get_spending_summary(from_date, to_date, account=None)`**
Spend grouped by category over a period, transfers excluded (same exclusion logic as
`balance.get_cashflow`: skip `is_transfer` and any category of type `Transfer`).
Returns `{"from_date", "to_date", "currency", "money_in", "money_out", "net",
"by_category": [{category, amount, count}]}`.
Reports in the **default currency only** (decision 2 in §12); the docstring must say so,
and the tool should note in its return when accounts in other currencies were skipped.

This is the tool that answers "what did I spend on food last month". Neither
`get_cashflow` nor `list_transactions` answers it well, which is why it exists rather
than making the model aggregate rows itself.

### Write tool — `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: false`

**`add_transaction(account, posting_date, direction, amount, description=None, category=None, counterparty=None, payment_mode=None, reference_number=None)`**

Creates one transaction via `frappe.get_doc(...).insert()` — never direct SQL — so the
whole `WalletTransaction.validate` chain fires: `validate_amount`, `set_signed_amount`,
`validate_against_opening_date`, `apply_categorization`, `set_dedup_hash`.

Docstring must state: `amount` is always **positive**; `direction` is `"In"` or `"Out"`
and is what records money leaving; `posting_date` is `YYYY-MM-DD`.

Returns the created transaction **plus the account's resulting balance**, so the model
can give the user a concrete confirmation rather than "done".

Inserts immediately — no `dry_run`, no two-step confirm (decision 1 in §12). The
resulting balance in the return payload is what makes a misparsed amount visible, and a
wrong entry is trivially deleted in the PWA.

---

## 6. File layout

```
wallet/mcp/
	__init__.py
	read.py          # MCP("wallet-read")  + whitelisted handle_mcp
	write.py         # MCP("wallet-write") + whitelisted handle_mcp
	endpoint.py      # serve(): mcp.handle() shim, see the correction in §4
	tools.py         # the five tool functions, plain, undecorated
	registry.py      # register_read_tools(mcp) / register_write_tools(mcp)
	resolve.py       # name -> docname resolution
	guard.py         # rollback-on-error wrapper
```

`registry.py` exists so the read tools are defined once and attached to both instances.
`mcp.tool()` returns a decorator that registers the function and hands it back unchanged,
so imperative registration is just:

```python
def register_read_tools(mcp):
	for fn, annotations in READ_TOOLS:
		mcp.tool(annotations=annotations)(fn)
```

Entry points are thin:

```python
# wallet/mcp/read.py
mcp = frappe_mcp.MCP("wallet-read")


@frappe.whitelist(methods=["GET", "POST"])
def handle_mcp() -> Response:
	return serve(mcp, register_read_tools)
```

---

## 7. Shared plumbing

### `resolve.py` — names, not hashes

`Wallet Account` and `Wallet Category` are both `autoname: hash`. Handing an LLM
`a1b2c3d4e5` as a category id is a quality disaster, and asking it to remember one across
turns is worse.

So: **every tool argument that identifies an account or a category accepts a human
name**, case-insensitively. On a miss, throw with the list of valid options — a failed
call that tells the model what it may say next is worth far more than a generic error.
Reads return both `id` and `name`, so the id is available if a caller wants it.

Resolution must be permission-aware (below), which also means a name lookup can never
leak another user's account.

### `guard.py` — rollback on error

`frappe_mcp/server/tools/handlers.py` catches **every** tool exception and returns
`isError: true` over HTTP 200. Frappe's request teardown then sees a successful request
and commits — so a `frappe.throw` partway through a write would leave partial state
committed.

Every write tool body is wrapped in a helper that catches, calls `frappe.db.rollback()`,
and re-raises a clean message. Applying it to read tools too is harmless and keeps the
rule "all tools go through the guard" rather than "remember which ones need it".

### Permission-awareness

`wallet/permissions.py` warns that `frappe.get_all` and `frappe.qb` bypass
`permission_query_conditions` entirely, and calls it the single most likely security bug
in the app. That applies verbatim here. **Every query in `wallet/mcp/` uses
`frappe.get_list`, or carries an explicit `owner = frappe.session.user` filter.** No bare
`get_all`. This is the first thing to grep for in review.

### Duplicate handling in `add_transaction`

`dedup_hash` is a **UNIQUE** column on `Wallet Transaction`. An insert that fingerprints
identically to an existing row raises a raw MariaDB duplicate-key error, which would
reach the model as `Error calling tool 'add_transaction': (1062, ...)`.

So `add_transaction` pre-computes `wallet.utils.dedup.build_dedup_hash` and, on a hit,
returns a clean structured refusal naming the existing transaction — "this duplicates
TXN-2026-00042 (2026-08-14, ₹450, Groceries)" — rather than letting the constraint fire.

---

## 8. Gotchas checklist

Carry these into review; each one was verified against this bench, not assumed.

- [ ] Werkzeug/pydantic pin conflict — installed `--no-deps`, `frappe-mcp` **not** in `pyproject.toml`
- [ ] Installed from git `main`, not PyPI 0.1.0
- [ ] Every write tool rolls back explicitly on exception
- [ ] `add_transaction` pre-checks `dedup_hash` before insert
- [ ] All account/category arguments accept names; errors list valid options
- [ ] Zero bare `frappe.get_all` in `wallet/mcp/`
- [ ] Every tool returns a dict at the top level
- [ ] Docstrings state the sign convention and date format
- [ ] README states the bearer token is session-wide, not endpoint-scoped

---

## 9. Build order

1. Install `frappe-mcp` (§4); confirm `import frappe_mcp` works in `bench console`.
2. `wallet/mcp/resolve.py` and `guard.py` — plumbing first, with tests.
3. `wallet/mcp/tools.py` — the four read tools.
4. `wallet/mcp/registry.py`, `read.py` — read endpoint live.
5. Verify read endpoint end to end (§10) before writing any write code.
6. `add_transaction` + `write.py`.
7. Verify write endpoint; README section on connecting.

---

## 10. Verification

**Static:** `frappe-mcp check --app wallet --verbose` — validates that handlers are
discovered and every tool's inferred `inputSchema` is well-formed.

**OAuth metadata**, before touching a client:

```bash
curl -s http://demo.localhost:8000/.well-known/oauth-protected-resource | jq
curl -s http://demo.localhost:8000/.well-known/oauth-authorization-server | jq
# expect a registration_endpoint in the second
```

**Interactive:** `npx @modelcontextprotocol/inspector`, Transport = **Streamable HTTP**,
run the OAuth flow, list tools, call each one.

**Claude Code:**

```bash
claude mcp add --transport http wallet-read \
	http://demo.localhost:8000/api/method/wallet.mcp.read.handle_mcp
```

Plain HTTP works here only because this bench runs with `developer_mode` on. Frappe
rejects dynamic client registration for any non-https `redirect_uri` otherwise, with no
loopback exemption — so a production site breaks the self-registration flow that MCP
clients rely on. See the warning in README.md.

**Automated:** `wallet/tests/test_mcp_tools.py` calls the tool functions directly under
`frappe.set_user(...)`. The cases that matter most:

- a second user's accounts, transactions and categories are invisible to the first —
  for every read tool
- name resolution cannot resolve another user's account name
- `add_transaction` with a negative amount, a date before `opening_date`, and an unknown
  category name all fail cleanly
- a duplicate `add_transaction` is refused by name, not by SQL error
- a failed write leaves nothing committed

---

## 11. Out of scope for phase 1

Deliberately excluded, roughly in the order they would come back:

- `update_transaction` (recategorize) — likely the first phase 2 addition
- delete transactions
- account and category CRUD
- statement import
- budgets — `Wallet Budget` is listed in `permissions.OWNED_DOCTYPES` but has no doctype
  directory yet; resolve that before exposing anything
- MCP prompts and resources (`frappe-mcp` gained prompt support in May 2026; resources
  are still unimplemented upstream)

---

## 12. Decisions

Settled before implementation. Recorded here because each one is a place where the
simpler option was chosen deliberately, not by default.

**1. `add_transaction` inserts immediately.** No `dry_run` flag, no preview-and-confirm
handshake. The return payload carries the resulting account balance, which surfaces a
misparsed amount right where the user will read it, and a bad entry is one tap to delete
in the PWA. A two-step write doubles every call and adds state for a risk the return
value already exposes. Revisit if real usage shows the model writing wrong amounts.

**2. `get_spending_summary` reports in the default currency only.** `get_overview`
buckets per currency because a dashboard must never add rupees to dollars in a headline
figure. The summary is answering a conversational question, and a nested per-currency
return would make the model work harder in the overwhelmingly common single-currency
case. The docstring states the limitation, and the return flags when other-currency
accounts were skipped rather than silently dropping them.

**3. Module layout is `wallet/mcp/` with `read.py` and `write.py`.** Endpoints are
`/api/method/wallet.mcp.read.handle_mcp` and `/api/method/wallet.mcp.write.handle_mcp`;
server names are `wallet-read` and `wallet-write`. A package rather than flat modules
because the MCP surface brings its own helpers (`resolve.py`, `guard.py`, `registry.py`,
`tools.py`) that have no meaning outside it — scattering those next to `hooks.py` would
bury them among the app's core modules.
