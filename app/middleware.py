"""Credential middleware: reads the three PayPal headers, 401s if any are
missing or invalid, and sets the request-scoped context vars for the
duration of the request (SOP S3.2/S3.3, AC6, AC11).

This is a bare ASGI middleware (not Starlette's BaseHTTPMiddleware) so it
can gate only the MCP route and leave /health untouched (SOP S1.1: health
must never depend on credentials), and so the finally/reset runs exactly
once per connection regardless of how the inner app streams its response.
"""

from __future__ import annotations

import json

from app.context import paypal_client_id, paypal_client_secret, paypal_environment

_HEADER_CLIENT_ID = b"x-paypal-client-id"
_HEADER_CLIENT_SECRET = b"x-paypal-client-secret"
_HEADER_ENVIRONMENT = b"x-paypal-environment"
_VALID_ENVIRONMENTS = {"sandbox", "live"}


class CredentialMiddleware:
    """Enforces the three required PayPal credential headers on `mcp_path`."""

    def __init__(self, app, mcp_path: str = "/mcp") -> None:
        self.app = app
        self.mcp_path = mcp_path

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path") != self.mcp_path:
            await self.app(scope, receive, send)
            return

        headers = {k: v for k, v in scope.get("headers", [])}
        client_id = headers.get(_HEADER_CLIENT_ID)
        client_secret = headers.get(_HEADER_CLIENT_SECRET)
        environment_raw = headers.get(_HEADER_ENVIRONMENT)
        environment = environment_raw.decode("latin-1").strip().lower() if environment_raw else None

        missing: list[str] = []
        if not client_id:
            missing.append("X-Paypal-Client-Id")
        if not client_secret:
            missing.append("X-Paypal-Client-Secret")
        if not environment:
            missing.append("X-Paypal-Environment")
        elif environment not in _VALID_ENVIRONMENTS:
            missing.append("X-Paypal-Environment (must be 'sandbox' or 'live')")

        if missing:
            await _send_401(send, missing)
            return

        id_token = paypal_client_id.set(client_id.decode("latin-1"))
        secret_token = paypal_client_secret.set(client_secret.decode("latin-1"))
        env_token = paypal_environment.set(environment)
        try:
            await self.app(scope, receive, send)
        finally:
            paypal_client_id.reset(id_token)
            paypal_client_secret.reset(secret_token)
            paypal_environment.reset(env_token)


async def _send_401(send, missing_headers: list[str]) -> None:
    body = json.dumps(
        {"error": "missing_credentials", "missing_headers": missing_headers},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
