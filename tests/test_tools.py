"""tools/list snapshot and per-tool success / error-mapping tests.

Traceability: test names match the `tests` field of the matching entry in
docs/tickets/PRD-21314.ac.json.
"""

from __future__ import annotations

import json

import httpx

from tests.conftest import SANDBOX_BASE

EXPECTED_TOOLS = {
    "paypal_create_order",
    "paypal_get_order",
    "paypal_capture_order",
    "paypal_get_capture",
    "paypal_refund_capture",
    "paypal_get_refund",
    "paypal_create_invoice",
    "paypal_send_invoice",
    "paypal_get_invoice",
    "paypal_list_invoices",
}


async def test_tools_list_snapshot_has_ten_tools(mcp):
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS
    assert len(tools) == 10

    by_name = {t.name: t for t in tools}
    assert by_name["paypal_get_order"].inputSchema["required"] == ["order_id"]
    assert by_name["paypal_create_order"].inputSchema["required"] == ["currency", "amount"]
    assert by_name["paypal_capture_order"].annotations.destructiveHint is True
    assert by_name["paypal_get_order"].annotations.readOnlyHint is True


# ---- AC1: create order ----------------------------------------------------


async def test_create_order_returns_id_and_status(paypal, call_tool):
    paypal.post(f"{SANDBOX_BASE}/v2/checkout/orders").mock(
        return_value=httpx.Response(201, json={"id": "ORDER1", "status": "CREATED"})
    )
    result = json.loads(await call_tool("paypal_create_order", {"currency": "USD", "amount": "25.00"}))
    assert result["id"] == "ORDER1"
    assert result["status"] in {"CREATED", "PAYER_ACTION_REQUIRED"}


async def test_create_order_response_never_echoes_secret(paypal, call_tool):
    paypal.post(f"{SANDBOX_BASE}/v2/checkout/orders").mock(
        return_value=httpx.Response(201, json={"id": "ORDER1", "status": "CREATED"})
    )
    text = await call_tool("paypal_create_order", {"currency": "USD", "amount": "25.00"})
    assert "placeholder-client-secret" not in text
    assert "client_secret" not in text.lower()


# ---- AC2: get order ---------------------------------------------------------


async def test_get_order_returns_status_and_amount(paypal, call_tool):
    paypal.get(f"{SANDBOX_BASE}/v2/checkout/orders/ORDER1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "ORDER1",
                "status": "APPROVED",
                "purchase_units": [{"amount": {"currency_code": "USD", "value": "25.00"}}],
            },
        )
    )
    result = json.loads(await call_tool("paypal_get_order", {"order_id": "ORDER1"}))
    assert result == {"id": "ORDER1", "status": "APPROVED", "amount": {"currency_code": "USD", "value": "25.00"}}


# ---- AC3: capture order -----------------------------------------------------


async def test_capture_order_returns_capture_matching_order_amount(paypal, call_tool):
    paypal.post(f"{SANDBOX_BASE}/v2/checkout/orders/ORDER1/capture").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "ORDER1",
                "status": "COMPLETED",
                "purchase_units": [
                    {
                        "amount": {"currency_code": "USD", "value": "25.00"},
                        "payments": {
                            "captures": [
                                {
                                    "id": "CAP1",
                                    "status": "COMPLETED",
                                    "amount": {"currency_code": "USD", "value": "25.00"},
                                }
                            ]
                        },
                    }
                ],
            },
        )
    )
    result = json.loads(await call_tool("paypal_capture_order", {"order_id": "ORDER1"}))
    assert result["id"] == "CAP1"
    assert result["status"] == "COMPLETED"
    assert result["amount"] == {"currency_code": "USD", "value": "25.00"}


# ---- AC4: refund capture -----------------------------------------------------


async def test_refund_capture_returns_refund_id_and_status(paypal, call_tool):
    paypal.post(f"{SANDBOX_BASE}/v2/payments/captures/CAP1/refund").mock(
        return_value=httpx.Response(201, json={"id": "REFUND1", "status": "COMPLETED"})
    )
    result = json.loads(
        await call_tool("paypal_refund_capture", {"capture_id": "CAP1", "amount": "10.00", "currency": "USD"})
    )
    assert result == {"id": "REFUND1", "status": "COMPLETED"}


# ---- AC5: not-found mapping ---------------------------------------------------


async def test_get_capture_not_found_maps_to_structured_error(paypal, call_tool):
    paypal.get(f"{SANDBOX_BASE}/v2/payments/captures/MISSING").mock(
        return_value=httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "message": "no such capture"})
    )
    result = json.loads(await call_tool("paypal_get_capture", {"capture_id": "MISSING"}))
    assert result["error"]["code"] == "not_found"
    assert result["error"]["retryable"] is False


# ---- AC8: create invoice -----------------------------------------------------


async def test_create_invoice_returns_draft_id(paypal, call_tool):
    paypal.post(f"{SANDBOX_BASE}/v2/invoicing/invoices").mock(
        return_value=httpx.Response(201, json={"id": "INV1", "status": "DRAFT"})
    )
    result = json.loads(
        await call_tool(
            "paypal_create_invoice",
            {
                "recipient_email": "customer@example.com",
                "items": [{"name": "Widget", "quantity": "1", "unit_amount": {"currency_code": "USD", "value": "10.00"}}],
            },
        )
    )
    assert result["id"] == "INV1"
    assert result["status"] == "DRAFT"


# ---- AC9: send invoice --------------------------------------------------------


async def test_send_invoice_returns_sent_status(paypal, call_tool):
    paypal.post(f"{SANDBOX_BASE}/v2/invoicing/invoices/INV1/send").mock(return_value=httpx.Response(202))
    paypal.get(f"{SANDBOX_BASE}/v2/invoicing/invoices/INV1").mock(
        return_value=httpx.Response(200, json={"id": "INV1", "status": "SENT"})
    )
    result = json.loads(await call_tool("paypal_send_invoice", {"invoice_id": "INV1"}))
    assert result == {"id": "INV1", "status": "SENT"}


# ---- AC10: list + pagination ---------------------------------------------------


async def test_list_invoices_default_limit_sets_has_more(paypal, call_tool):
    items = [{"id": f"INV{i}", "status": "DRAFT"} for i in range(20)]
    paypal.get(f"{SANDBOX_BASE}/v2/invoicing/invoices").mock(
        return_value=httpx.Response(200, json={"items": items, "total_items": 37})
    )
    result = json.loads(await call_tool("paypal_list_invoices", {}))
    assert len(result["items"]) == 20
    assert result["has_more"] is True


# ---- AC13: idempotent create (header-forwarding half) --------------------------


async def test_create_order_forwards_request_id_as_paypal_request_id_header(paypal, call_tool):
    route = paypal.post(f"{SANDBOX_BASE}/v2/checkout/orders").mock(
        return_value=httpx.Response(201, json={"id": "ORDER1", "status": "CREATED"})
    )
    await call_tool(
        "paypal_create_order", {"currency": "USD", "amount": "25.00", "request_id": "x"}
    )
    assert route.calls.last.request.headers["PayPal-Request-Id"] == "x"
