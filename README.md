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

Wallet can act as an [MCP](https://modelcontextprotocol.io) server, so an AI agent can
read your accounts and transactions and add new ones. Two endpoints, so read access can be
granted without write access:

| Endpoint | Tools |
|---|---|
| `/api/method/wallet.mcp.read.handle_mcp` | `list_accounts`, `list_transactions`, `list_categories`, `get_spending_summary` |
| `/api/method/wallet.mcp.write.handle_mcp` | the above, plus `add_transaction` |

#### Setup

`frappe-mcp` is not in `pyproject.toml`: it pins `Werkzeug==3.1.3` and `pydantic~=2.11.7`,
while Frappe pins newer versions of both, so a normal resolve would downgrade Werkzeug and
break the bench. Install it without its dependencies instead:

```bash
./env/bin/pip install jsonschema
./env/bin/pip install --no-deps git+https://github.com/frappe/mcp.git
bench restart
```

Verify with `./env/bin/frappe-mcp check --app wallet`.

Requires a Frappe version with the OAuth2 metadata endpoints
([frappe#33188](https://github.com/frappe/frappe/pull/33188)) — v16 or later. No other
configuration is needed: `OAuth Settings` enables dynamic client registration and the
`.well-known` metadata endpoints by default.

#### Connecting a client

There is no API key to copy. Paste the endpoint URL into your MCP client; it registers
itself, opens your normal Frappe login, and receives a token once you approve.

```bash
claude mcp add --transport http wallet \
	https://<your-site>/api/method/wallet.mcp.read.handle_mcp
```

Remote clients require HTTPS; `localhost` origins may use plain HTTP for local development.

> [!IMPORTANT]
> A Frappe OAuth bearer token is session-wide, not endpoint-scoped — `validate_oauth`
> derives a token's required scopes from the token itself. A token issued for the
> read-only endpoint can still reach any whitelisted method on the site as you. The
> read/write split limits blast radius with a well-behaved client; it is not a sandbox
> against a hostile one.

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
