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
so it holds however the endpoint is reached. Which tools an agent should reach for is
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
