# Security boundaries

What actually keeps one user's money separate from another's, and — more importantly —
where those boundaries stop. Everything here was pulled out of the README, where it was
scaring readers who only wanted to install the app.

---

## Owner isolation

Every personal record is scoped to the user who created it, using the framework's own
`owner` column. There is no `user` Link field; a second copy would just be one more thing
to keep in sync.

Enforced in three places, deliberately:

1. `if_owner = 1` on the Wallet User role in each doctype's permissions → `frappe.get_doc`
   and the form view
2. `permission_query_conditions` (`wallet/permissions.py`) → list view, report view,
   `frappe.get_list`
3. `has_permission` (same module) → direct document access checks

Only `Administrator` is exempt. `System Manager` is deliberately **not** — it is an
ordinary role that the account holder themselves almost always has, and exempting it would
mean their own list views quietly mix in other people's transactions.

### The rule that keeps being broken

`frappe.get_all` and `frappe.qb` **bypass `permission_query_conditions` entirely.**

Any aggregate must either use `frappe.get_list` or carry an explicit
`owner = frappe.session.user` filter. This is the single most likely security bug in this
app.

Grepping for `get_all` and `frappe.qb` in review is necessary but not sufficient — see
finding 1 in [`audit-2026-08-30.md`](audit-2026-08-30.md), where the leak was in framework
code that queries on the app's behalf and no grep of this repo would have found it.
`frappe.desk.treeview.get_children` listed every user's category names; it is now
overridden in `hooks.py` by `wallet/treeview.py`, which goes through `frappe.get_list`.
When you add a whitelisted framework method to a page that shows personal data, check
what it queries before trusting it.

Current deliberate uses of `get_all`, all reviewed:

| Location | Why it is safe |
|---|---|
| `install.py:get_wallet_users` | queries `User`, not a wallet doctype |
| `categorization.py:get_rules` | explicit `owner` filter |
| `utils/dedup.py:occurrence_index` | scoped to one account, which is already the caller's |
| `wallet_statement_import.py` dedup lookup | scoped to `self.account` |
| `wallet_category.py:get_descendant_names` | explicit `owner` filter |
| `api/balance.py:rebuild_all_balances` | runs as the scheduler, across all users, by design |

---

## What MCP does and does not contain

Wallet has no MCP endpoint of its own. Agents connect to Frappe's built-in server at
`/api/v2/mcp` (v16.53+), which authenticates through the site's OAuth stack and runs every
tool through REST API v2, so `has_permission` and `permission_query_conditions` apply to it
exactly as they do to the PWA.

### The agent gets generic CRUD, so the write gate is on the document

The built-in server offers every connected agent `create_document`, `update_document`,
`delete_document`, `call_method` and `call_document_method`. An agent never has to go
through `wallet.mcp.tools.add_transaction` to write a Wallet Transaction, so a check inside
that function would cover nothing.

The gate is therefore enforced in `wallet/mcp/gate.py`, wired as `validate`, `on_trash`
and `before_rename` on every Wallet doctype (`MCP_GATED_DOCTYPES` in `hooks.py`). A write
over MCP needs **both**:

- `Wallet Settings.allow_mcp_writes`, the site switch. Wallet Settings is itself gated,
  so an agent cannot switch it on.
- `User.wallet_allow_mcp_writes`, the user's own opt-in, default off. It is set from the
  PWA's *More* screen (`wallet.api.mcp_access.set_mcp_writes`). `User.validate` refuses
  any change to it over MCP, and any change made by someone other than that user,
  Administrator included.

**Decision (issue #22, audit finding 6): per-user opt-in, not site-wide alone.** One
administrator switching on the site flag must not open the write path for every user
who has connected an agent. The opt-in is a field on `User` rather than a Frappe user
default because `frappe.client.set_default` is whitelisted: an agent could opt itself in
with one `call_method`. A field changes through a document save, where the hook above
catches it.
The two whitelisted methods that write with `frappe.db.set_value` instead of a document
save (`rebuild_balances`, `Wallet Account.refresh_cached_balance`) call `gate.check()`
themselves. **A new raw write reachable from a whitelisted method needs the same call.**

"This is an MCP request" is `frappe.local.mcp_request`, which `frappe.mcp.transport` sets.
That is a framework internal, so `test_gate.py` pins it: a rename upstream fails CI rather
than silently opening the gate.

The read methods in `wallet.mcp.tools` are whitelisted for GET only. `call_method` runs
such a method as a GET and rolls back afterwards, so the framework guarantees they write
nothing.

### A Frappe OAuth bearer token is session-wide

`validate_oauth` derives a token's required scopes from the token itself, not from the URL
being called. A token issued to an MCP client can reach **any** whitelisted method and the
REST API on the site as that user. The built-in server's generic tools therefore grant
nothing the token could not already do. `allow_mcp_writes` closes the Wallet write path
over MCP specifically. **It does not contain a client you do not trust**: the same token
can still call the REST API directly.

### Connect as yourself, never as Administrator

`wallet/permissions.py` exempts `Administrator` deliberately, as a break-glass account. An
MCP client connected as Administrator therefore bypasses owner isolation entirely, and
every answer silently aggregates all users' data — with no error and nothing in the
response to indicate it happened.

### `readOnlyHint` is a hint

The built-in tools carry MCP's `readOnlyHint` / `destructiveHint` annotations, and clients
use them to gate and confirm. They are not a server-side control; `allow_mcp_writes` is.

---

## Client registration

Dynamic client registration is on by default. Loopback redirect URIs
(`http://localhost:<port>/...`, `http://127.0.0.1:<port>/...`) are accepted as secure, so
MCP clients self-register on production sites without `developer_mode`
(`_is_secure_redirect_uri` in `frappe/integrations/utils.py`). Any other non-https
redirect still requires `developer_mode`.

Browser-based clients such as the MCP Inspector additionally need their origin listed in
`OAuth Settings → Allowed Public Client Origins`, which is empty by default; the MCP
transport refuses a cross-origin request unless `allow_cors` lists it. Native clients
(Claude Code, Claude Desktop) need neither.

---

## Smaller boundaries worth knowing

**Statement files.** `Wallet Statement Import.statement_file` is an Attach field, i.e.
arbitrary text, so it can be pointed at any file URL on the site including another user's
private upload. `get_file_content` checks that the file is attached to this very import,
and otherwise falls back to `check_permission("read")` plus an explicit owner check.

**Statement passwords.** Cleared from the document as soon as a parse succeeds.
`preview_layout` is POST rather than GET specifically so the password never lands in a URL,
browser history, proxy log or access log.

**Category parents.** The parent Link carries `ignore_user_permissions`, and the lookup
bypasses permission hooks, so `validate_parent_type` does an explicit owner check. Without
it a crafted request could graft a category onto another user's tree, rewriting their
`lft`/`rgt`.

**Account balances.** `get_account_balance` calls `frappe.has_permission` explicitly,
because `frappe.db.get_value` bypasses the permission hooks and would otherwise let an
authenticated caller read any account's opening balance and currency by guessing its name.
