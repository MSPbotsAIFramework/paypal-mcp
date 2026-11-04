"""Credential middleware tests: missing headers, bad credentials, concurrent
isolation, and retry-budget exhaustion under sustained 429s.

These go through the real ASGI app (app/server.create_app()), unlike
test_tools.py, because the behavior under test lives in the middleware and
in concurrent-request scheduling, not in tool logic.

Traceability: test names match the `tests` field of the matching entry in
docs/tickets/PRD-21314.ac.json.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging

import httpx
import pytest
import respx

from tests.conftest import SANDBOX_BASE


def _parse_sse_json(text: str) -> dict:
    """Streamable HTTP responses are one SSE event; pull the JSON payload out of it."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    raise AssertionError(f"no 'data:' line in response body: {text!r}")


@pytest.fixture
async def http_client(http_app):
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _rpc(method: str, params: dict | None = None, id_: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


_ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


# ---- AC6: missing credential header -> 401 before any upstream call -------------


async def test_missing_credential_header_returns_401_before_any_upstream_call(http_client):
    with respx.mock(assert_all_called=False) as router:
        token_route = router.post(f"{SANDBOX_BASE}/v1/oauth2/token")

        resp = await http_client.post(
            "/mcp",
            headers={**_ACCEPT, "X-Paypal-Client-Id": "cid", "X-Paypal-Environment": "sandbox"},
            json=_rpc("tools/list"),
        )

        assert resp.status_code == 401
        body = resp.json()
        assert body["missing_headers"] == ["X-Paypal-Client-Secret"]
        assert token_route.call_count == 0  # no PayPal call was attempted


async def test_missing_all_credential_headers_lists_all_three(http_client):
    resp = await http_client.post("/mcp", headers=_ACCEPT, json=_rpc("tools/list"))
    assert resp.status_code == 401
    assert set(resp.json()["missing_headers"]) == {
        "X-Paypal-Client-Id",
        "X-Paypal-Client-Secret",
        "X-Paypal-Environment",
    }


async def test_health_endpoint_does_not_require_credentials(http_client):
    resp = await http_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---- AC7: bad credentials -> structured unauthorized, secret never leaked -------


async def test_bad_credentials_return_unauthorized_without_leaking_secret(http_client, caplog):
    secret = "super-secret-value"
    with caplog.at_level(logging.DEBUG):
        with respx.mock(assert_all_called=False) as router:
            router.post(f"{SANDBOX_BASE}/v1/oauth2/token").mock(
                return_value=httpx.Response(401, json={"error": "invalid_client"})
            )
            resp = await http_client.post(
                "/mcp",
                headers={
                    **_ACCEPT,
                    "X-Paypal-Client-Id": "cid",
                    "X-Paypal-Client-Secret": secret,
                    "X-Paypal-Environment": "sandbox",
                },
                json=_rpc(
                    "tools/call", {"name": "paypal_get_order", "arguments": {"order_id": "X"}}
                ),
            )

    assert resp.status_code == 200
    payload = _parse_sse_json(resp.text)
    tool_text = payload["result"]["content"][0]["text"]
    result = json.loads(tool_text)
    assert result == {
        "error": {
            "code": "unauthorized",
            "message": "PayPal rejected the supplied credentials",
            "retryable": False,
        }
    }
    assert secret not in resp.text
    assert all(secret not in record.getMessage() for record in caplog.records)


# ---- AC11: concurrent requests never cross-contaminate credentials/data ---------


async def test_concurrent_requests_do_not_cross_contaminate_context(http_client):
    with respx.mock(assert_all_called=False) as router:

        def mint_token(request: httpx.Request) -> httpx.Response:
            basic = _decode_basic(request.headers["Authorization"])
            account = "A" if basic.startswith("cid-a:") else "B"
            return httpx.Response(200, json={"access_token": f"token-{account}", "token_type": "Bearer", "expires_in": 32400})

        router.post(f"{SANDBOX_BASE}/v1/oauth2/token").mock(side_effect=mint_token)

        def get_order(request: httpx.Request) -> httpx.Response:
            token = request.headers["Authorization"]
            if token == "Bearer token-A":
                return httpx.Response(
                    200,
                    json={"id": "SHARED", "status": "APPROVED",
                          "purchase_units": [{"amount": {"currency_code": "USD", "value": "11.00"}}]},
                )
            return httpx.Response(
                200,
                json={"id": "SHARED", "status": "COMPLETED",
                      "purchase_units": [{"amount": {"currency_code": "EUR", "value": "22.00"}}]},
            )

        router.get(f"{SANDBOX_BASE}/v2/checkout/orders/SHARED").mock(side_effect=get_order)

        async def call(client_id: str, client_secret: str) -> dict:
            resp = await http_client.post(
                "/mcp",
                headers={
                    **_ACCEPT,
                    "X-Paypal-Client-Id": client_id,
                    "X-Paypal-Client-Secret": client_secret,
                    "X-Paypal-Environment": "sandbox",
                },
                json=_rpc(
                    "tools/call", {"name": "paypal_get_order", "arguments": {"order_id": "SHARED"}}
                ),
            )
            payload = _parse_sse_json(resp.text)
            return json.loads(payload["result"]["content"][0]["text"])

        result_a, result_b = await asyncio.gather(
            call("cid-a", "secret-a"),
            call("cid-b", "secret-b"),
        )

    assert result_a == {"id": "SHARED", "status": "APPROVED", "amount": {"currency_code": "USD", "value": "11.00"}}
    assert result_b == {"id": "SHARED", "status": "COMPLETED", "amount": {"currency_code": "EUR", "value": "22.00"}}
    # Neither call's credentials or result leaked into the other's response.
    assert "secret-b" not in json.dumps(result_a)
    assert "secret-a" not in json.dumps(result_b)
    assert "EUR" not in json.dumps(result_a)
    assert "USD" not in json.dumps(result_b)


def _decode_basic(header: str) -> str:
    _scheme, _, value = header.partition(" ")
    return base64.b64decode(value).decode()


# ---- AC12: persistent 429 exhausts the retry budget -> rate_limited ------------


async def test_persistent_429_exhausts_retry_budget_and_returns_rate_limited(http_client):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{SANDBOX_BASE}/v1/oauth2/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok", "token_type": "Bearer", "expires_in": 32400})
        )
        route = router.get(f"{SANDBOX_BASE}/v2/checkout/orders/RL1").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0"}, json={"name": "RATE_LIMIT_REACHED"})
        )

        resp = await http_client.post(
            "/mcp",
            headers={
                **_ACCEPT,
                "X-Paypal-Client-Id": "cid",
                "X-Paypal-Client-Secret": "secret",
                "X-Paypal-Environment": "sandbox",
            },
            json=_rpc("tools/call", {"name": "paypal_get_order", "arguments": {"order_id": "RL1"}}),
        )

    payload = _parse_sse_json(resp.text)
    result = json.loads(payload["result"]["content"][0]["text"])
    assert result["error"]["code"] == "rate_limited"
    assert result["error"]["retryable"] is True
    # Initial attempt + the configured retry budget, no more, no less.
    assert route.call_count == 4
