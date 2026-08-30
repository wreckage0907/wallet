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

## Planning / Spec-ing

Use tracer bullets (from *The Pragmatic Programmer*). When building systems, write code
that gets you feedback as quickly as possible. Tracer bullets are small slices of
functionality that go through all layers of the system, letting you test and validate the
approach early. This surfaces problems and confirms the architecture is sound before
significant time goes into development.

## Testing

Use the `agent-browser` skill to test the feature e2e.

- Site: `http://demo.localhost` (Frappe Manager / Docker, `fm__demo_localhost__*`)
- Sign in as `girish.raghav2004@gmail.com`. `site_config.json` still records
  `admin_password: admin`, but that pair is stale — the login 401s. Ask for the
  password rather than guessing; do not commit it here.
- Python tests: `bench --site demo.localhost run-tests --app wallet`
- Frontend dev server: `cd frontend && yarn dev` (port 8080, proxies to the bench)

> Note for e2e: connecting or testing as **Administrator** bypasses the owner isolation
> everything else relies on (`permissions.py` exempts it). To exercise isolation, use a
> real user.

## Pull requests

Never put the Claude Code session link in a PR description. It is noise to every
reviewer but one, and it does not resolve for anybody else. The description should
carry only what someone reviewing the diff needs.
