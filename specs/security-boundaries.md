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

Grepping for `get_all` in review is necessary but not sufficient — see finding 1 in
[`audit-2026-08-30.md`](audit-2026-08-30.md), where the leak was in framework code that
queries on the app's behalf and no grep of this repo would have found it.

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

## What the MCP endpoint does and does not contain

### A Frappe OAuth bearer token is session-wide

`validate_oauth` derives a token's required scopes from the token itself, not from the URL
being called. A token issued for Wallet can reach **any** whitelisted method on the site as
that user.

This is why the MCP server is one endpoint rather than a read URL and a write URL.
Splitting them looks like a boundary and is not one: a token issued for a "read-only" URL
can POST to the write URL just as easily.

`Wallet Settings.allow_mcp_writes` closes the Wallet write path specifically, checked
inside the tool body so it holds however the endpoint is reached. **It does not contain a
client you do not trust.**

### Connect as yourself, never as Administrator

`wallet/permissions.py` exempts `Administrator` deliberately, as a break-glass account. An
MCP client connected as Administrator therefore bypasses owner isolation entirely, and
every answer silently aggregates all users' data — with no error and nothing in the
response to indicate it happened.

### `readOnlyHint` is a hint

Which tools an agent should reach for is expressed with MCP's own `readOnlyHint` /
`destructiveHint` annotations. Clients use them to gate and confirm. They are not a
server-side control; `allow_mcp_writes` is.

---

## Dynamic client registration needs HTTPS

Dynamic client registration requires **every** `redirect_uri` to be `https`, unless the
site runs with `developer_mode` on (`frappe/integrations/utils.py`). There is no loopback
exemption.

MCP clients register loopback redirects like `http://localhost:<port>/callback`, so on a
production site the self-registration flow fails with `redirect_uris must be https`.
Either register an OAuth Client by hand, or keep `developer_mode` on.

This is a `developer_mode` distinction, not a local-versus-remote one.

Browser-based clients such as the MCP Inspector additionally need their origin listed in
`OAuth Settings → Allowed Public Client Origins`, which is empty by default. Native
clients (Claude Code, Claude Desktop) do not.

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
