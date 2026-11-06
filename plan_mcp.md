# Plan: move Wallet onto Frappe's built-in MCP server

Status: implemented on `feat/builtin-mcp`. Supersedes the `frappe-mcp` plan this file used
to hold. Closes #15 (MCP uninstallable on Frappe Cloud) and #22 (per-user opt-in for MCP
writes).

## Why

Frappe ships an MCP server in core from **v16.53.0** (and on `develop`): `frappe/mcp/`,
served at `/api/v2/mcp`. Wallet's own endpoint exists only because it didn't. That
endpoint costs us a dependency installed by hand with `--no-deps` (it pins `Werkzeug==3.1.3`
and `pydantic~=2.11.7` against Frappe's newer pins), a pinned git commit in CI, a shim
around `@mcp.register()`, and a rollback guard.

## What the built-in server is (read from `frappe/mcp/`, v16.53+)

- **One endpoint per site:** `POST /api/v2/mcp`, Streamable HTTP, JSON responses, no
  session store. Protocol `2025-11-25` and `2026-07-28`.
- **Switch:** `System Settings → Enable MCP` (default on). `Server Name` and
  `Agent Instructions` are also there; the latter is appended to the `instructions` every
  client receives on connect.
- **Who may connect:** an authenticated user with the `Desk User` role, which every System
  User has implicitly. Wallet users are System Users, so this holds for them.
- **Auth:** the existing Frappe OAuth stack. A 401 carries `WWW-Authenticate` pointing at
  `/.well-known/oauth-protected-resource`; dynamic client registration is on by default.
  Loopback redirect URIs (`http://localhost:<port>/...`) are now accepted **without
  `developer_mode`**, so MCP clients self-register on production sites too.
- **Tools are fixed, not pluggable.** `frappe.mcp.tools.registry()` is a hardcoded tuple of
  13 generic tools: `search_doctypes`, `get_doctype_schema`, `search_methods`,
  `get_method_schema`, `list_document_methods`, `list_documents`, `get_document`,
  `count_documents`, `create_document`, `update_document`, `delete_document`,
  `call_method`, `call_document_method`. There is no hook for an app to add a tool.
- **Permissions:** every tool goes through REST API v2, so `has_permission` and
  `permission_query_conditions` apply. Verified on demo.localhost: a Wallet user cannot
  read, count or delete another user's transactions through it.
- **Errors roll back:** a failed tool call propagates to `frappe.app`, which rolls back,
  then `transport.error_response` turns it into an `isError` tool result. This is
  exactly what `wallet/mcp/guard.py` did by hand.
- **`call_method`** runs any whitelisted method. One whitelisted for GET only (not POST) is
  run as a GET and **rolled back afterwards**: a framework-enforced read-only path.
- **`search_methods` / `get_method_schema`** read the API discovery index: dotted path,
  params with types, and the docstring.

## What that means for Wallet

1. **The curated tools survive as whitelisted methods.** There is no way to register
   `list_accounts` as a first-class tool, but the reason those tools exist still holds:
   accounts and categories are `autoname: hash`, and a model cannot carry `a1b2c3d4e5`
   across turns, nor aggregate a spending summary from paginated `list_documents` calls.
   So `wallet.mcp.tools.*` stay, whitelisted, and the agent reaches them with
   `call_method`. Reads are `methods=["GET"]`, so the framework runs them read-only and
   rolls them back. `add_transaction` is `methods=["POST"]`.
   *Trade-off:* one level of indirection for the agent (`search_methods "wallet"` then
   `call_method`) instead of five named tools. Discovery finds them: the server's
   `instructions` already list "Wallet (wallet)" among installed apps.

2. **The write gate moves from the tool body to the document layer.** Built-in MCP hands
   every agent `create_document` / `update_document` / `delete_document` / `call_method`.
   With `allow_mcp_writes` **off**, both `create_document` and
   `call_method → create_transaction` wrote rows on demo.localhost. A check inside
   `add_transaction` no longer covers the write path, so:
   - `wallet.mcp.gate` reads `frappe.local.mcp_request`, which `frappe.mcp.transport`
     sets for the whole of an MCP request.
   - `doc_events` on every Wallet doctype (`validate`, `on_trash`, `before_rename`) refuse
     the write over MCP while `allow_mcp_writes` is off. This includes `Wallet Settings`
     itself, so an agent can never turn its own write access on.
   - The two whitelisted paths that write with `frappe.db.set_value` instead of a document
     save (`rebuild_balances`, `Wallet Account.refresh_cached_balance`) call the gate
     explicitly.
   - Outside MCP (PWA, desk, REST) nothing changes.
   - A test pins the `frappe.local.mcp_request` contract, so an upstream rename fails CI
     instead of silently opening the gate.

3. **Per-user opt-in (#22).** A write over MCP needs the site switch *and*
   `User.wallet_allow_mcp_writes`, default off, set by the user from the PWA's *More*
   screen. `User.validate` refuses a change to it over MCP or by anyone else. It is a field,
   not a user default, because `frappe.client.set_default` is whitelisted and an agent could
   opt itself in.

4. **Delete:** `registry.py`, `guard.py`, the `frappe-mcp` install step in CI, the README's
   `--no-deps` instructions, and the guard test. `wallet.mcp.handle_mcp` stays as a stub
   that answers `410 Gone` with the new URL, so stale client configs get a controlled error
   (#15's acceptance) rather than a traceback.

5. **Raise the floor** to `frappe >= 16.53.0` in `[tool.bench.frappe-dependencies]`.

6. **Docs:** the endpoint becomes `/api/v2/mcp`. Update README, AGENTS.md,
   `specs/security-boundaries.md` (the gate's new location, the HTTPS caveat that no longer
   applies, the generic tools agents now see), and the `allow_mcp_writes` description.

## What does not change

- Owner isolation: it was always the permission hooks, and the built-in server goes
  through them.
- The bearer token is still session-wide. Generic CRUD over MCP grants nothing the same
  token could not already do against `/api/v2/document/...`.
- Connecting as Administrator still bypasses isolation. Connect as yourself.

## Verification

- Python suite: `bench --site demo.localhost run-tests --app wallet`.
- In-process, as a Wallet user through `frappe.mcp.tools.call`: `call_method` reaches each
  curated tool, and isolation holds. The gate refuses `create_document`,
  `update_document`, `delete_document`, `call_method add_transaction` and
  `update_document Wallet Settings` with writes off, and allows them with writes on.
- Over HTTP, as a fresh Wallet user (`mcp-e2e@example.com`), both protocol revisions:
  `initialize`, `tools/list`, `search_methods`, every `wallet.mcp.tools` method, isolation,
  each switch refusing on its own, the agent's three ways of opting itself in refused, a
  failed write leaving no rows, and the old URL answering 410. Done.
- PWA: the *More* screen's toggle, all three states, persisted across reload. Done.

## Local bench (done)

frappe `develop` cbd6d59 (May) → 91cf805 (6 Nov), with `frappe/mcp`. erpnext, hrms
(→ `develop`), crm, raven, wiki, drive, next_pms were pulled to their latest. `whatsapp`
was installed, because CRM now requires it. Site migrated.
