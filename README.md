# paypal-mcp

MCP server wrapping a subset of the [PayPal REST API](https://developer.paypal.com/docs/api/overview/)
(Checkout Orders/Payments and Invoicing) for the MSPbots Agent platform. Built
from PayPal's public API documentation; not affiliated with or endorsed by
PayPal.

- **Transport**: MCP Streamable HTTP (`POST /mcp`), stateless -- no session
  pinning, no local persistent state.
- **Stack**: Python 3.12, [FastMCP](https://gofastmcp.com/), `httpx`.
- **License**: Apache-2.0. Copyright MSPbots.ai.

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

Every `/mcp` request must carry all three headers below. The gateway injects
the connected tenant's own values; this service never stores or caches them.

| Header | Required | Type | Notes |
|---|---|---|---|
| `X-Paypal-Client-Id` | yes | string | PayPal REST app Client ID (PayPal Developer Dashboard -> Apps & Credentials) |
| `X-Paypal-Client-Secret` | yes | password | PayPal REST app Secret, same location |
| `X-Paypal-Environment` | yes | string, enum `sandbox` \| `live` | Selects `api-m.sandbox.paypal.com` vs `api-m.paypal.com` as the upstream host. No default -- an explicit value is required so the service never silently guesses sandbox vs. live. |

Missing any of the three -> `401` with a JSON body listing exactly which
headers are missing, before any call to PayPal is attempted.

## Tools

10 tools, split across Checkout Orders/Payments and Invoicing. Scope for
this first version; Subscriptions, Payouts, Disputes, and receiving webhooks
are out of scope (see "Non-goals" below).

| Tool | What it does | Annotations |
|---|---|---|
| `paypal_create_order` | Create a checkout order for a one-off payment | write |
| `paypal_get_order` | Get an order's status and amount | read-only |
| `paypal_capture_order` | Capture payment on an approved order | destructive |
| `paypal_get_capture` | Get a capture's status and amount | read-only |
| `paypal_refund_capture` | Refund a completed capture, fully or partially | destructive |
| `paypal_get_refund` | Get a refund's status and amount | read-only |
| `paypal_create_invoice` | Create a draft invoice | write |
| `paypal_send_invoice` | Send a draft invoice to its recipient by email | destructive |
| `paypal_get_invoice` | Get an invoice's status | read-only |
| `paypal_list_invoices` | List invoices, paginated (default limit 20, hard cap 100) | read-only |

## Non-goals (this version)

- **Subscriptions** (recurring billing) -- different object model and retry semantics; no subscription use case is named in this service's scope.
- **Payouts** (mass payments to third parties) -- a materially higher-risk, irreversible money-movement surface.
- **Disputes** (chargeback/dispute management) -- a distinct workflow with its own evidence-upload contract.
- **Receiving PayPal webhooks** -- this service is a stateless, per-request tool the gateway calls; it does not expose a public inbound endpoint.
- Any PayPal-provided SDK or "AI-ready" toolkit -- this service is a clean-room implementation against PayPal's public REST API.

These are tracked as candidates for follow-up tickets once a concrete use case names one of them.

## Error handling

Every tool returns a JSON string. On failure, it returns a structured
error envelope instead of raising:

```json
{"error": {"code": "not_found", "message": "No capture with id ... on this account.", "retryable": false}}
```

`code` is one of: `not_configured`, `unauthorized`, `not_found`,
`invalid_argument`, `rate_limited`, `upstream_error`.

## Local development

```bash
uv sync
uv run pytest
uv run python -m app   # starts the server on 0.0.0.0:8080
```

Smoke test with placeholder credentials (sandbox calls will fail
authentication against real PayPal, which is expected without real
credentials -- this only proves the transport and header handling work):

```bash
curl -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H 'X-Paypal-Client-Id: test' -H 'X-Paypal-Client-Secret: test' -H 'X-Paypal-Environment: sandbox' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Build the container image:

```bash
docker build --platform linux/amd64 -t paypal-mcp:dev .
```
