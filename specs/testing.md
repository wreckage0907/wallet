# Testing

Ground rules for the Python suite. The Playwright suite is documented in
[`development.md`](development.md).

## Where a test file goes

**`wallet/tests/` mirrors `wallet/`.** A module's tests live at the same path under
`wallet/tests/`, with `test_` prefixed to the filename:

| Source | Test |
|---|---|
| `wallet/api/balance.py` | `wallet/tests/api/test_balance.py` |
| `wallet/statement/parse.py` | `wallet/tests/statement/test_parse.py` |
| `wallet/utils/dedup.py` | `wallet/tests/utils/test_dedup.py` |
| `wallet/categorization.py` | `wallet/tests/test_categorization.py` |

Every mirror directory carries an `__init__.py`, or the runner cannot import it.

**Doctypes are the exception.** A doctype's controller and its document events are tested
beside the controller, the way Frappe generates them:

| Source | Test |
|---|---|
| `wallet/wallet/doctype/wallet_transaction/wallet_transaction.py` | `.../wallet_transaction/test_wallet_transaction.py` |

That covers `validate`, `after_insert`, `on_update` and friends **for a doctype we own**.
A document event we attach in `hooks.py` to a doctype we do *not* own has no such home, so
it mirrors the hook instead, under `doc_events/` named for the doctype it fires on:

| Hook | Test |
|---|---|
| `doc_events["User"]["after_insert"]` | `wallet/tests/doc_events/test_user.py` |

**`wallet/tests/fixtures.py` mirrors nothing.** It is the one support module under
`tests/`, and it holds the fixture builders every suite shares. A suite that needs a
fixture nobody else does keeps it local.

## How a test is written

**`UnitTestCase` for pure functions, `IntegrationTestCase` when a row is needed.**
`wallet/statement/parse.py` and `detect.py` never touch the database and their tests must
not either — they are the fast half of the suite, and keeping them that way is deliberate.

**A suite owns its fixtures end to end.** `purge()` runs in both `setUpClass` and
`tearDownClass`: the first so a crashed run does not poison the next one, the second so
the dev site is left as it was found. These tests run against a real database, not a
scratch one.

**Never test as Administrator.** `permissions.py` exempts it from owner isolation, so an
isolation assertion made under Administrator passes no matter how broken the query
conditions are. Suites use real users built by `fixtures.make_user`. The one legitimate
exception is code that is *documented* to run as Administrator — the nightly
`rebuild_all_balances` — and its test says so.

**Name the test after the behaviour, not the function.**
`test_credit_card_is_a_liability` over `test_validate`. The name is what a failure prints,
and "validate failed" tells the reader nothing.

**Assert on the thing that would actually break.** A fingerprint test asserts that two
hashes differ, not that a hash equals a hard-coded digest — the digest is an
implementation detail and pinning it turns every refactor into a test rewrite.

## Running them

```bash
bench --site <site> run-tests --app wallet
bench --site <site> run-tests --app wallet --module wallet.tests.utils.test_dedup
```

CI runs the whole suite on every pull request; see the CI table in
[`development.md`](development.md).
