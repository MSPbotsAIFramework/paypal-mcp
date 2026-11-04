"""Shared fixtures: a fresh FastMCP instance, mocked PayPal responses, and
placeholder credential headers.

Tests never talk to real PayPal -- every PayPal HTTP call is intercepted by
respx. The in-process fastmcp.Client talks to the FastMCP server object
directly (no HTTP, no real network), so these are true unit tests.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import Client

from app.context import paypal_client_id, paypal_client_secret, paypal_environment
from app.server import build_mcp

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"

HEADERS = {
    "X-Paypal-Client-Id": "placeholder-client-id",
    "X-Paypal-Client-Secret": "placeholder-client-secret",
    "X-Paypal-Environment": "sandbox",
}


@pytest.fixture
def paypal():
    """A respx router scoped to the PayPal sandbox host, with the OAuth2 token
    mint pre-mocked to succeed. Tests add their own endpoint mocks on top.
    """
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{SANDBOX_BASE}/v1/oauth2/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "fake-access-token", "token_type": "Bearer", "expires_in": 32400}
            )
        )
        yield router


@pytest.fixture
def mcp():
    return build_mcp()


@asynccontextmanager
async def run_lifespan(app):
    """Drive an ASGI app's lifespan protocol by hand.

    httpx.ASGITransport talks http scope only; it never sends the lifespan
    startup/shutdown messages a real server (uvicorn) sends. Without them,
    FastMCP's StreamableHTTPSessionManager never initializes its task group
    and every /mcp call fails with "Task group is not initialized" -- the
    exact pitfall SOP S7 warns about, just surfacing in the test harness
    instead of production. This is the minimal fix: drive the two lifespan
    messages directly against the app callable.
    """
    receive_q: asyncio.Queue = asyncio.Queue()
    send_q: asyncio.Queue = asyncio.Queue()

    async def receive():
        return await receive_q.get()

    async def send(message):
        await send_q.put(message)

    task = asyncio.create_task(app({"type": "lifespan"}, receive, send))
    await receive_q.put({"type": "lifespan.startup"})
    started = await send_q.get()
    assert started["type"] == "lifespan.startup.complete", started
    try:
        yield
    finally:
        await receive_q.put({"type": "lifespan.shutdown"})
        stopped = await send_q.get()
        assert stopped["type"] == "lifespan.shutdown.complete", stopped
        await task


@pytest.fixture
async def http_app():
    """The real ASGI app (app/server.create_app()) with its lifespan running."""
    from app.server import create_app

    app = create_app()
    async with run_lifespan(app):
        yield app


@pytest.fixture
def credentials():
    """Set the three credential context vars for the duration of a test,
    simulating what app/middleware.py does for a real request. Needed
    because test_tools.py calls tools through an in-process Client that
    bypasses the ASGI middleware layer on purpose (these are tool-logic
    unit tests, not middleware tests -- see test_middleware.py for those).
    """
    tokens = (
        paypal_client_id.set(HEADERS["X-Paypal-Client-Id"]),
        paypal_client_secret.set(HEADERS["X-Paypal-Client-Secret"]),
        paypal_environment.set("sandbox"),
    )
    try:
        yield
    finally:
        paypal_client_id.reset(tokens[0])
        paypal_client_secret.reset(tokens[1])
        paypal_environment.reset(tokens[2])


@pytest.fixture
async def call_tool(mcp, credentials):
    """Call a tool by name against the shared `mcp` fixture, returning its text result."""

    async def _call(name: str, arguments: dict):
        async with Client(mcp) as client:
            result = await client.call_tool(name, arguments, raise_on_error=False)
            return result.content[0].text if result.content else None

    return _call
