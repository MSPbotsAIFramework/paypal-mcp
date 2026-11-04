"""Shared tool-call scaffolding: build a client, run the call, map every
failure to the structured error envelope, never let an exception escape
(SOP S4.1: tools never raise back through tools/call).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.errors import PaypalMcpError
from app.logging_utils import log_event
from app.paypal_client import PaypalClient
from app.serialize import dump


async def run_with_client(
    client_factory: Callable[[], PaypalClient],
    fn: Callable[[PaypalClient], Awaitable[dict[str, Any]]],
    *,
    tool_name: str = "",
) -> str:
    """Build a client from `client_factory`, run `fn(client)`, serialize the result.

    Any PaypalMcpError raised by `client_factory` or `fn` becomes the JSON
    error envelope instead of propagating. Any other exception is mapped to
    `upstream_error` as a last-resort guard -- it should not normally be
    reached, since app/paypal_client.py maps every PayPal failure mode
    itself.
    """
    try:
        client = client_factory()
    except PaypalMcpError as exc:
        log_event(event="tool_call", tool=tool_name, outcome="error", code=exc.code)
        return exc.to_json()

    trace_id = getattr(client, "trace_id", None)
    try:
        result = await fn(client)
        log_event(event="tool_call", tool=tool_name, trace_id=trace_id, outcome="ok")
        return dump(result)
    except PaypalMcpError as exc:
        log_event(event="tool_call", tool=tool_name, trace_id=trace_id, outcome="error", code=exc.code)
        return exc.to_json()
    except Exception as exc:  # pragma: no cover - defensive backstop, see docstring
        log_event(event="tool_call", tool=tool_name, trace_id=trace_id, outcome="error", code="upstream_error")
        return PaypalMcpError("upstream_error", f"Unexpected failure: {exc}").to_json()
    finally:
        await client.aclose()
