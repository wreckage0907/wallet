# How it works

The model behind the screens: what Wallet stores, how one person's money is kept from
another's, how a statement file becomes transactions, and how a re-import is recognised.

## 📦 Data model

| DocType | What it holds |
|---|---|
| `Wallet Account` | one bank account, card, wallet or loan |
| `Wallet Transaction` | the ledger — one row per transaction |
| `Wallet Category` | a tree of Expense / Income / Transfer categories |
| `Wallet Categorization Rule` | narration pattern → category, with priority |
| `Wallet Statement Import` | one import, with its staged rows as a child table |
| `Wallet Statement Format` | a remembered column layout for a bank's export |
| `Wallet Bank` | shared bank reference data |
| `Wallet Settings` | site-wide defaults, including the site half of the MCP write gate |

Account and category names are unique **per user**, not globally — both doctypes are
`autoname: hash` precisely so two people can each have a "HDFC Savings" and a "Groceries".

## 🔒 Data isolation

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

## 📄 The import pipeline

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

## 🔁 De-duplication

Three tiers, in order:

1. **Reference number** (UTR, cheque number, transaction id) — already a unique key per account.
2. **Date + signed amount + normalised narration, disambiguated by the running balance.**
   Two genuinely distinct ₹50 payments to the same merchant on the same day would otherwise
   collide; their running balances differ, which separates them for free with no dependence
   on row order and no sensitivity to re-imports or deletions.
3. **An occurrence ordinal**, when the bank supplies neither. The weakest tier: delete one of
   a duplicate pair and re-import, and the ordinal no longer lines up.

Fingerprints are stamped once, on insert, and never recomputed — so correcting a transaction
later never changes which statement row it came from.

Because the fingerprint lives on `Wallet Transaction` rather than on the import, it also
catches a **manual entry that duplicates an imported row**, and survives deleting the import.
