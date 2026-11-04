"""FastMCP server factory: wires the credential middleware, the health
probe, and the tool modules into one Streamable HTTP ASGI app.
"""

from __future__ import annotations

from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from fastmcp import FastMCP

from app.context import current_credentials
from app.errors import PaypalMcpError
from app.middleware import CredentialMiddleware
from app.paypal_client import PaypalClient
from app.tools import invoicing, orders, payments

INSTRUCTIONS = """\
This service wraps a subset of the PayPal REST API (Checkout Orders/Payments
and Invoicing) for an MSPbots Agent acting on a connected PayPal business
account. Use the order tools to collect a one-off payment (create -> wait
for buyer approval -> capture -> optionally refund); use the invoice tools
to bill a customer by email (create a draft -> send it -> list/check status).
Every call requires PayPal credential headers scoped to one connected
account; there is no cross-account or cross-tenant access. Money-moving
calls (capture, refund, send) are irreversible or customer-facing -- confirm
intent with the user before calling them.\
"""


def client_factory() -> PaypalClient:
    """Build a PaypalClient from the current request's credential context.

    Raises PaypalMcpError("not_configured", ...) if called outside a request
    the credential middleware has populated. In normal operation this never
    happens -- the middleware already rejects such requests with 401 before
    any tool runs (SOP S3.2) -- this is defense in depth, not the primary
    guard.
    """
    try:
        client_id, client_secret, environment = current_credentials()
    except RuntimeError as exc:
        raise PaypalMcpError("not_configured", str(exc)) from None
    return PaypalClient(client_id, client_secret, environment)


def build_mcp() -> FastMCP:
    # stateless_http is set on http_app() below, not here: this fastmcp
    # version (2.14.7) deprecated passing it to the FastMCP constructor in
    # favor of setting it per-transport.
    mcp = FastMCP(name="paypal-mcp", instructions=INSTRUCTIONS)

    orders.register(mcp, client_factory)
    payments.register(mcp, client_factory)
    invoicing.register(mcp, client_factory)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        # Pure local probe -- never calls PayPal (SOP S1.1).
        return JSONResponse({"status": "ok"})

    return mcp


def create_app():
    """Build the ASGI app: Streamable HTTP `/mcp` + `GET /health`.

    The credential middleware only gates `/mcp` (see app/middleware.py), so
    `/health` stays reachable even with no/invalid headers. `stateless_http`
    is set at both the server and the http_app level so no MCP session is
    pinned to a particular worker/instance (SOP S1.3).
    """
    mcp = build_mcp()
    return mcp.http_app(
        path="/mcp",
        stateless_http=True,
        middleware=[Middleware(CredentialMiddleware, mcp_path="/mcp")],
    )
