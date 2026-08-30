# Wallet

Personal finance for Frappe. Add your bank accounts, drop in the statement files your bank
emails you, and Wallet parses, de-duplicates and categorizes every row — then shows you
where the money went, on your phone.

Built for Indian retail banking: dd/mm dates, `Dr`/`Cr` suffixes, running-balance columns,
password-protected xlsx, and out-of-the-box rules for Swiggy, Zomato, UPI, FASTag, NACH
EMIs and the rest.

<!-- SCREENSHOT:HERO -->

## What it does

**Statement import that actually works on real bank files.** Point it at the xlsx your bank
emailed you — encrypted, with three rows of branch details above the table and a totals row
below — and it finds the transaction table, works out which column is which, and stages
every row for you to review before a single transaction is written.

**De-duplication that survives overlapping statements.** Statements overlap month to month.
Wallet fingerprints each transaction from its own content — reference number, or date +
amount + narration disambiguated by the running balance — so re-importing an overlapping
period is a no-op, and a manual entry that duplicates an imported row is caught too.

**Auto-categorization from your own rules.** Ships with ~20 rules tuned for Indian bank
narrations and a two-level category tree (Food & Dining › Food Delivery, Transport › Fuel,
…). Rules match on description, counterparty or reference, by substring, prefix, exact match
or regex, filtered by direction, account and amount range.

**Balances that cannot drift.** An account's balance is always recomputed as
`opening_balance + SUM(signed_amount)`, never incremented into a stored counter. Multi-currency
accounts are totalled per currency and never silently added together.

**A reconciliation number you can trust.** After an import, Wallet compares its computed
closing balance against the closing balance the statement itself states. One number that
checks parsing, sign convention and de-duplication all at once.

**An MCP server.** Ask your AI assistant what you spent on groceries last month, or have it
record a cash payment — with writes off by default.

## Screens

Wallet has two faces. The PWA at `/wallet` is for looking — mobile-first, installable,
works offline. The Frappe desk at `/app/wallet` is for the heavier work: creating accounts,
running imports, editing categorization rules.

<!-- SCREENSHOT:PWA -->

<!-- SCREENSHOT:DESK -->

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/wreckage0907/wallet --branch main
bench install-app wallet
```

The frontend is not committed — build it once after install, or the PWA and the app icon
will 404:

```bash
cd apps/wallet/frontend
yarn install
yarn build
```

Requires Frappe v16. `msoffcrypto-tool` (for password-protected statements) is installed by
bench from `pyproject.toml`. The MCP server needs one extra manual step — see below.

Installing creates a **Wallet User** role but does not assign it. Give it to anyone who
should keep their own accounts; `System Manager` also works.

## Getting started

1. **Wallet › Wallet Account › New.** Name it, pick a type, set the opening balance and the
   date that balance was true as of. Transactions dated before the opening date are
   rejected rather than silently excluded from the balance.
2. **Wallet › Import Statement › New.** Pick the account, attach the file, and enter the
   password if your bank encrypts it.
3. **Parse Statement.** Wallet finds the header row, maps the columns, parses every row and
   marks each one New, Duplicate or Error.
4. **Review the preview.** Fix a category, skip a row. Nothing has been written yet. If a
   column was mapped wrong, correct the mapping and re-parse — never hand-edit the values.
5. **Import N Rows.** Each row commits in its own savepoint, so one bad row cannot take the
   batch down with it. Check `balance_variance` afterwards: zero means everything reconciles.
6. **Save as Format** (optional). Wallet remembers the column layout by its header
   signature, so the next statement from the same bank skips steps 3 and 4 entirely.

Your categories and rules are seeded per user the first time you use the app. Deleting or
renaming one sticks — they are defaults, not fixtures. **More › Restore default
categories** brings back anything you deleted and want again, leaving your renames alone.

## How it works

### Data model

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

### Data isolation

Every personal record is scoped to the user who created it, using the framework's own
`owner` column. Isolation is enforced in three places at once — `if_owner` on the role's
doctype permissions, `permission_query_conditions` for list and report queries, and
`has_permission` for direct document access.

`System Manager` is deliberately **not** exempt. It is an ordinary role that the account
holder themselves almost always has, and exempting it would mean your own list views quietly
mix in other people's transactions. Only `Administrator` is exempt, purely as the
break-glass account.

Account and category names are unique **per user**, not globally — both doctypes are
`autoname: hash` precisely so two people can each have a "HDFC Savings" and a "Groceries".

### The import pipeline

```
file → decrypt → read grid → detect header → stage rows → review → commit → reconcile
```

Header detection scores every row near the top of the file by how many target fields its
cells look like, and takes the best. A row only qualifies if it yields a date column plus at
least one amount column — which is what separates a real header from an address line that
happens to contain the word "Date".

Summary and footer rows are recognised *after* failing to parse as a transaction, never
before. Checking markers first meant a real fuel payment to "TotalEnergies" matched a
generic "total" marker and was silently dropped.

dd/mm vs mm/dd is genuinely ambiguous per cell, so it is decided per *column*: any value
whose first component exceeds 12 can only be a day, and that settles it for the whole column.

Staged rows live in a real child table rather than a JSON blob, because the whole point of a
preview is that you can edit it before committing.

### De-duplication

Three tiers, in order:

1. **Reference number** (UTR, cheque number, transaction id) — already a unique key per
   account.
2. **Date + signed amount + normalised narration, disambiguated by the running balance.**
   Two genuinely distinct ₹50 payments to the same merchant on the same day would otherwise
   collide; their running balances differ, which separates them for free with no dependence
   on row order.
3. **An occurrence ordinal**, when the bank supplies neither. The weakest tier: delete one
   of a duplicate pair and re-import, and the ordinal no longer lines up. There is nothing
   better available when a statement carries neither a reference number nor a balance column.

Fingerprints are stamped once, on insert, and never recomputed — so correcting a transaction
later never changes which statement row it came from.

## MCP server

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

### Setup

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

### Connecting a client

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

## Development

```bash
cd apps/wallet/frontend
yarn install
yarn dev          # Vite on :8080, proxied to the bench
yarn build        # writes into wallet/public/frontend/ and wallet/www/wallet.html
```

Build output is gitignored, so a fresh clone always needs `yarn build`.

```bash
bench --site <site> run-tests --app wallet
```

`.gitignore` blocks `*.xlsx`, `*.xls`, `*.csv` and `*.pdf` at the repo root. Real bank
statements are the natural test fixture and must never be committed.

### Known gaps

- The PWA is read-only; adding and editing happen in the desk at `/app/wallet`.
- Test coverage is MCP-only. The statement parser, header detection, de-duplication and the
  balance engine have no tests yet.
- `Wallet Budget` is referenced in `permissions.py` and `hooks.py` but the doctype does not
  exist.
- `pyproject.toml` declares `requires-python = ">=3.14"`, which is ahead of what most
  benches run.

## Contributing

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

## License

MIT
