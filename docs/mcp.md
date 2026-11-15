# 🤖 MCP server

Wallet works with Frappe's built-in [MCP](https://modelcontextprotocol.io) server, so an AI
agent can read your accounts and transactions and record new ones. There is nothing extra
to install: the server ships with Frappe v16.53 and later, one endpoint per site.

```
/api/v2/mcp
```

The agent gets Frappe's generic tools (`list_documents`, `create_document`, `call_method`,
…), which go through the same permission hooks as everything else — owner isolation
included. On top of those, Wallet adds methods shaped for a model, reached with
`call_method`:

| Method `wallet.mcp.tools.` | | |
|---|---|---|
| `list_accounts` | balances, including what is owed on a credit card | 🔍 read |
| `list_transactions` | filter by account, date, category, direction, or free text | 🔍 read |
| `list_categories` | the names the other methods accept | 🔍 read |
| `get_spending_summary` | money in, money out and spend per category over a period | 🔍 read |
| `add_transaction` | record one transaction | ✍️ write |

They take account and category *names*, not hash ids. The reads are whitelisted for GET
only, so the server runs them read-only and rolls them back. Agents find all of them with
`search_methods`.

**Writes are off by default, twice over.** An agent can change your Wallet data only while
both switches are on:

1. `Allow MCP Writes` in Wallet Settings, which the site's administrator controls.
2. **Let AI agents make changes**, under *More* in the app, which only you can turn on
   for yourself.

The gate is enforced on every Wallet document, not in one tool, so it holds for the generic
`create_document` / `update_document` / `delete_document` as well. An agent cannot flip
either switch: Wallet Settings is gated too, and your own opt-in refuses any change made
over MCP.

Still pointing at the old `/api/method/wallet.mcp.handle_mcp`? It answers with a JSON-RPC
error that names the new URL.

Point your MCP client at the endpoint URL. It registers itself, opens your normal Frappe
login, and receives a token once you approve. There is no API key to copy.

```bash
claude mcp add --transport http wallet https://<your-site>/api/v2/mcp
```

## ⚙️ Setup

Requires Frappe **v16.53.0** or later. Nothing else needs configuring:

- `System Settings → Enable MCP` is on by default. `Agent Instructions` there is sent to
  every client that connects, a good place to say "personal finances live in Wallet; use
  `wallet.mcp.tools`".
- `OAuth Settings` enables dynamic client registration and the `.well-known` metadata
  endpoints by default, and loopback redirect URIs (`http://localhost:<port>/…`) are
  accepted without `developer_mode`.

Connect as yourself, never as Administrator: Administrator is exempt from owner isolation.
The server accepts any user with desk access, which every Wallet user has.

Verify by listing the tools:

```bash
curl -s -X POST -H "Authorization: token <api_key>:<api_secret>" \
	-H "Content-Type: application/json" -H "Accept: application/json" \
	-d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
	https://<your-site>/api/v2/mcp
```
