<p align="center">
  <img src="docs/images/pwa-dashboard.png" width="300" alt="Wallet dashboard showing net worth, monthly cashflow and account balances">
</p>

<h1 align="center"><samp>Wallet : Your Bank Statements, Finally Readable</samp></h1>

<p align="center">
  <samp>
    Personal finance for Frappe. Add your bank accounts, drop in the statement files your bank emails you,<br>
    and Wallet parses, de-duplicates and categorizes every row &mdash; then shows you where the money went, on your phone.
  </samp>
</p>

<p align="center">
  <img alt="Frappe v16" src="https://img.shields.io/badge/Frappe-v16-0089ff?style=flat-square">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61dafb?style=flat-square">
  <img alt="PWA" src="https://img.shields.io/badge/PWA-installable-5a0fc8?style=flat-square">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-server-000000?style=flat-square">
  <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
</p>

<samp>

> Built for Indian retail banking: `dd/mm` dates, `Dr`/`Cr` suffixes, running-balance columns,
> password-protected xlsx, and out-of-the-box rules for Swiggy, Zomato, UPI, FASTag and NACH EMIs.

</samp>

<br>

# ✨ Features

<table align="center">
  <tr>
    <td width="50%" valign="top">
      <h3 align="center">Statement import that survives real bank files</h3>
      <samp>Point it at the xlsx your bank emailed you &mdash; encrypted, with three rows of branch details above the table and a totals row below. Wallet finds the transaction table, works out which column is which, and stages every row for review before a single transaction is written.</samp>
    </td>
    <td width="50%" valign="top">
      <h3 align="center">De-duplication across overlapping statements</h3>
      <samp>Statements overlap month to month. Wallet fingerprints each transaction from its own content &mdash; reference number, or date + amount + narration disambiguated by the running balance &mdash; so re-importing an overlapping period is a no-op.</samp>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3 align="center">Auto-categorization from your own rules</h3>
      <samp>Ships with ~20 rules tuned for Indian bank narrations and a two-level category tree. Rules match on description, counterparty or reference &mdash; by substring, prefix, exact match or regex &mdash; filtered by direction, account and amount range.</samp>
    </td>
    <td width="50%" valign="top">
      <h3 align="center">Balances that cannot drift</h3>
      <samp>A balance is always recomputed as <code>opening_balance + SUM(signed_amount)</code>, never incremented into a stored counter. Multi-currency accounts are totalled per currency and never silently added together.</samp>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3 align="center">A reconciliation number you can trust</h3>
      <samp>After an import, Wallet compares its computed closing balance against the one the statement itself states. A single number that checks parsing, sign convention and de-duplication all at once.</samp>
    </td>
    <td width="50%" valign="top">
      <h3 align="center">An MCP server, with writes off by default</h3>
      <samp>Ask your AI assistant what you spent on groceries last month, or have it record a cash payment. Five tools, one endpoint, and a write gate that lives inside the tool rather than in the URL.</samp>
    </td>
  </tr>
</table>

<br>

# 📱 Preview

<table align="center">
  <tr>
    <td width="33%" align="center" valign="top">
      <h3 align="center">Everything in one number</h3>
      <samp>Net worth, this month's money in and out, and every account balance &mdash; computed in two queries, not one per account.</samp>
      <br><br>
      <img src="docs/images/pwa-dashboard.png" alt="Dashboard with net worth, monthly cashflow and account list">
    </td>
    <td width="33%" align="center" valign="top">
      <h3 align="center">Accounts, and what they really hold</h3>
      <samp>Savings, cards, cash and loans together. A spent-on credit card shows as a negative balance, so the combined total is a plain sum.</samp>
      <br><br>
      <img src="docs/images/pwa-accounts.png" alt="Account list with balances and a combined total">
    </td>
    <td width="33%" align="center" valign="top">
      <h3 align="center">Activity that reads like a diary</h3>
      <samp>Transactions grouped by day rather than an undifferentiated wall, filterable to just what you spent or just what came in.</samp>
      <br><br>
      <img src="docs/images/pwa-transactions.png" alt="Transactions grouped by day with direction filters">
    </td>
  </tr>
</table>

<samp>Wallet has two faces. The PWA at <code>/wallet</code> is for looking &mdash; mobile-first, installable, works offline. The Frappe desk at <code>/app/wallet</code> is for the heavier work.</samp>

<p align="center">
  <img src="docs/images/desk-workspace.png" width="90%" alt="Wallet desk workspace with shortcuts to accounts, transactions, imports and categories">
</p>

<samp>The reconciliation block is the thing to look at after an import &mdash; Wallet's computed closing balance against the one the statement states.</samp>

<table align="center">
  <tr>
    <td width="50%" align="center" valign="top">
      <h3 align="center">✅ Reconciled</h3>
      <samp>Variance is zero. Every row parsed, signed and de-duplicated correctly.</samp>
      <br><br>
      <img src="docs/images/desk-import.png" alt="A completed import with a zero variance and a green reconciled banner">
    </td>
    <td width="50%" align="center" valign="top">
      <h3 align="center">⚠️ Off by ₹300</h3>
      <samp>1,500 rows imported and it still says so, instead of letting a mis-parsed row pass quietly.</samp>
      <br><br>
      <img src="docs/images/desk-import-variance.png" alt="A completed import of 1500 rows reporting a variance of minus 300 rupees">
    </td>
  </tr>
</table>

<br>

# ⚙️ Installation

<table>
<tr>
<td width="48.5%" valign="top">

<samp>

## 📝 Prerequisites

1. **Frappe Bench** with a **v16** site
2. **Python 3.11+**
3. **Node 18+** and **yarn**
4. **MariaDB** (via bench)
5. `msoffcrypto-tool` — installed by bench from `pyproject.toml`

<br>

## 🔮 Optional

- **`frappe-mcp`** — only for the MCP server, installed by hand (see **MCP server** below)
- **`developer_mode`** — only for MCP client self-registration

</samp>

</td>
<td width="48.5%" valign="top">

<samp>

## 🪴 Usage

#### 1. Install the app:

    bench get-app https://github.com/wreckage0907/wallet --branch main
    bench install-app wallet

#### 2. Build the frontend (not committed):

    cd apps/wallet/frontend
    yarn install
    yarn build

#### 3. Assign the role

<samp>Install creates a **Wallet User** role but does not assign it. Give it to anyone who should keep their own accounts; `System Manager` works too.</samp>

#### 4. Open it:

    /wallet        the PWA
    /app/wallet    the desk workspace

</samp>

</td>
</tr>
</table>

> [!IMPORTANT]
> Step 2 is not optional. Build output is gitignored, so a fresh clone that skips `yarn build`
> gets a 404 for the PWA **and** for the app icon on the `/apps` screen.

<br>

# 🚀 Getting started

<samp>

| | Step | What happens |
|---|---|---|
| **1** | **Wallet › Wallet Account › New** | Name it, pick a type, set the opening balance and the date it was true as of. Transactions dated before the opening date are rejected rather than silently dropped from the balance. |
| **2** | **Wallet › Import Statement › New** | Pick the account, attach the file, enter the password if your bank encrypts it. |
| **3** | **Parse Statement** | Wallet finds the header row, maps the columns, parses every row and marks each one New, Duplicate or Error. |
| **4** | **Review the preview** | Fix a category, skip a row. Nothing is written yet. If a column was mapped wrong, correct the mapping and re-parse — never hand-edit the values. |
| **5** | **Import N Rows** | Each row commits in its own savepoint, so one bad row cannot take the batch down. Check the variance afterwards. |
| **6** | **Save as Format** *(optional)* | Wallet remembers the layout by its header signature, so the next statement from the same bank skips steps 3 and 4. |

</samp>

<samp>Your categories and rules are seeded per user the first time you use the app. Deleting or renaming one sticks — they are defaults, not fixtures. **More › Restore default categories** brings back anything you deleted and want again, leaving your renames alone.</samp>

<br>

# 🧠 How it works

<details>
<summary><h3>📦 Data model</h3></summary>
<br>
<samp>

| DocType | What it holds |
|---|---|
| `Wallet Account` | one bank account, card, wallet or loan |
| `Wallet Transaction` | the ledger — one row per transaction |
| `Wallet Category` | a tree of Expense / Income / Transfer categories |
| `Wallet Categorization Rule` | narration pattern → category, with priority |
| `Wallet Statement Import` | one import, with its staged rows as a child table |
| `Wallet Statement Format` | a remembered column layout for a bank's export |
| `Wallet Bank` | shared bank reference data |
| `Wallet Settings` | site-wide defaults, including the MCP write gate |

Account and category names are unique **per user**, not globally — both doctypes are
`autoname: hash` precisely so two people can each have a "HDFC Savings" and a "Groceries".

</samp>
</details>

<details>
<summary><h3>🔒 Data isolation</h3></summary>
<br>
<samp>

Every personal record is scoped to the user who created it, using the framework's own
`owner` column. There is no `user` Link field — a second copy would just be one more thing
to keep in sync.

Isolation is enforced in three places at once:

1. `if_owner` on the Wallet User role's doctype permissions → form view
2. `permission_query_conditions` → list view, report view, `frappe.get_list`
3. `has_permission` → direct document access

`System Manager` is deliberately **not** exempt. It is an ordinary role that the account
holder themselves almost always has, and exempting it would mean your own list views quietly
mix in other people's transactions. Only `Administrator` is exempt, purely as the
break-glass account for recovery.

</samp>

> ### ⚠️ Warning
> `frappe.get_all` and `frappe.qb` bypass `permission_query_conditions` entirely. Any aggregate
> must use `frappe.get_list` or carry an explicit `owner` filter. This is the single most likely
> security bug in this app — see **Known gaps** below for one that is currently live.

</details>

<details>
<summary><h3>📄 The import pipeline</h3></summary>
<br>
<samp>

```
file → decrypt → read grid → detect header → stage rows → review → commit → reconcile
```

**Header detection** scores every row near the top of the file by how many target fields its
cells look like, and takes the best. A row only qualifies if it yields a date column plus at
least one amount column — which is what separates a real header from an address line that
happens to contain the word "Date".

**Footer detection is date-gated.** Summary rows are recognised *after* failing to parse as a
transaction, never before. Checking markers first meant a real fuel payment to "TotalEnergies"
matched a generic "total" marker and was silently dropped.

**dd/mm vs mm/dd is decided per column**, not per cell: any value whose first component
exceeds 12 can only be a day, and that settles it for every other value in the column.

**Staged rows live in a real child table**, not a JSON blob, because the whole point of a
preview is that you can edit it before committing.

</samp>
</details>

<details>
<summary><h3>🔁 De-duplication</h3></summary>
<br>
<samp>

Three tiers, in order:

1. **Reference number** (UTR, cheque number, transaction id) — already a unique key per account.
2. **Date + signed amount + normalised narration, disambiguated by the running balance.**
   Two genuinely distinct ₹50 payments to the same merchant on the same day would otherwise
   collide; their running balances differ, which separates them for free with no dependence
   on row order and no sensitivity to re-imports or deletions.
3. **An occurrence ordinal**, when the bank supplies neither. The weakest tier: delete one of
   a duplicate pair and re-import, and the ordinal no longer lines up. There is nothing better
   available when a statement carries neither a reference number nor a balance column.

Fingerprints are stamped once, on insert, and never recomputed — so correcting a transaction
later never changes which statement row it came from.

Because the fingerprint lives on `Wallet Transaction` rather than on the import, it also
catches a **manual entry that duplicates an imported row**, and survives deleting the import.

</samp>
</details>

<br>

# 🤖 MCP server

<samp>

Wallet can act as an [MCP](https://modelcontextprotocol.io) server, so an AI agent can read
your accounts and transactions and record new ones.

```
/api/method/wallet.mcp.handle_mcp
```

| Tool | | |
|---|---|---|
| `list_accounts` | balances, including what is owed on a credit card | 🔍 read |
| `list_transactions` | filter by account, date, category, direction, or free text | 🔍 read |
| `list_categories` | the names the other tools accept | 🔍 read |
| `get_spending_summary` | money in, money out and spend per category over a period | 🔍 read |
| `add_transaction` | record one transaction | ✍️ write |

**One endpoint, not one per access level.** Splitting reads and writes across two URLs looks
like a boundary and is not one: a Frappe OAuth bearer token is session-wide, so a token issued
for a "read-only" URL can POST to the write URL just as easily. Instead, **writes are off by
default** and enabled with `Allow MCP Writes` in Wallet Settings — checked inside the tool
body, so it holds however the endpoint is reached.

That setting is a site-wide Single, not a per-user opt-in: on a multi-user site, turning it on
opens the write path for every connected agent, each still confined to its own owner's records.

</samp>

<details>
<summary><h3>⚙️ Setup</h3></summary>
<br>
<samp>

`frappe-mcp` is **not** in `pyproject.toml`: it pins `Werkzeug==3.1.3` and `pydantic~=2.11.7`,
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
container or image rebuild, a fresh `bench init`, or a Frappe Cloud deploy will not have it,
and the endpoint will fail with `No module named 'frappe_mcp'`. Re-run the two commands above.
The rest of the app is unaffected — nothing else imports `frappe_mcp`.

Requires a Frappe version with the OAuth2 metadata endpoints
([frappe#33188](https://github.com/frappe/frappe/pull/33188)) — v16 or later. Nothing else
needs configuring: `OAuth Settings` enables dynamic client registration and the `.well-known`
metadata endpoints by default.

Verify by listing the tools, as a user with the `Wallet User` or `System Manager` role:

```bash
curl -s -X POST -H "Authorization: token <api_key>:<api_secret>" \
	-H "Content-Type: application/json" \
	-d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
	https://<your-site>/api/method/wallet.mcp.handle_mcp
```

`frappe-mcp check` reports this handler as "not properly registered". That is expected: it
looks for the `@mcp.register()` decorator, which this app deliberately does not use — see
`wallet/mcp/__init__.py` for why it breaks Frappe's app resolution.

</samp>
</details>

<details>
<summary><h3>🔌 Connecting a client</h3></summary>
<br>
<samp>

There is no API key to copy. Paste the endpoint URL into your MCP client; it registers itself,
opens your normal Frappe login, and receives a token once you approve.

```bash
claude mcp add --transport http wallet \
	https://<your-site>/api/method/wallet.mcp.handle_mcp
```

</samp>

> ### ⚠️ Warning
> Dynamic client registration requires **every** `redirect_uri` to be `https`, unless the site
> runs with `developer_mode` on. There is no loopback exemption. MCP clients register loopback
> redirects like `http://localhost:<port>/callback`, so on a production site the
> self-registration flow fails with `redirect_uris must be https`. Either register an OAuth
> Client by hand, or keep `developer_mode` on. This is a `developer_mode` distinction, not a
> local-versus-remote one.

<samp>Browser-based clients such as the MCP Inspector additionally need their origin listed in `OAuth Settings → Allowed Public Client Origins`, which is empty by default. Native clients (Claude Code, Claude Desktop) do not.</samp>

> ### ❗ Important
> A Frappe OAuth bearer token is session-wide, not endpoint-scoped. A token issued for Wallet
> can reach any whitelisted method on the site as you. `Allow MCP Writes` closes the Wallet
> write path specifically; it does not contain a client you do not trust.
>
> Connecting as **Administrator** bypasses the owner-based isolation the tools rely on, so
> every answer would silently aggregate all users' data. **Connect as your own user.**

</details>

<br>

# 🧪 Development

<table>
<tr>
<td width="48.5%" valign="top">

<samp>

## Frontend

    cd apps/wallet/frontend
    yarn install
    yarn dev      # Vite on :8080, proxied to bench
    yarn build    # → wallet/public/frontend/

Build output is gitignored, so a fresh clone always needs `yarn build`.

</samp>

</td>
<td width="48.5%" valign="top">

<samp>

## Backend

    bench --site <site> run-tests --app wallet

    cd apps/wallet
    pre-commit install

Pre-commit runs `ruff`, `eslint`, `prettier` and `pyupgrade`.

</samp>

</td>
</tr>
</table>

> [!CAUTION]
> `.gitignore` blocks `*.xlsx`, `*.xls`, `*.csv` and `*.pdf`. Real bank statements are the
> natural test fixture and must never be committed.

<br>

# ⚠️ Known gaps

<samp>

**The desk tree view for `Wallet Category` leaks other users' category names.**
Frappe's `frappe.desk.treeview._get_children` builds a raw `frappe.qb` query, and `frappe.qb`
bypasses `permission_query_conditions` — the exact failure mode `wallet/permissions.py` warns
about. Opening one of those documents is still correctly refused with a `PermissionError`, so
this is name enumeration, not a record read, and it affects only `Wallet Category` (the app's
only tree doctype). The fix is a `wallet_category_tree.js` pointing
`frappe.treeview_settings` at an owner-filtered `get_tree_nodes`.

**The PWA is read-only.** Adding and editing happen in the desk at `/app/wallet` — the one
context the desk is worst at.

**Test coverage is MCP-only.** 29 tests, all in `wallet/tests/test_mcp_tools.py`. The statement
parser, header detection, de-duplication and the balance engine have none — and `parse.py` and
`detect.py` are pure functions over plain data, the cheapest possible things to cover.

**`Wallet Budget` does not exist.** It is referenced in `permissions.py` and `hooks.py`, so
permission hooks are registered for a doctype that was never built.

**`pyproject.toml` declares `requires-python = ">=3.14"`**, which is ahead of what most benches
run — a plain `pip install -e .` would refuse.

**The MCP install is not reproducible.** `frappe-mcp` lives only in the bench virtualenv and
nothing in the repo restores it.

</samp>

<br>

<hr>

<p align="center">
  <samp>MIT &middot; built on <a href="https://frappeframework.com">Frappe</a></samp>
</p>
