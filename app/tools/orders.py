"""PayPal Checkout Orders v2 tools: create, get, capture."""

from __future__ import annotations

from typing import Any

from app.paypal_client import PaypalClient
from app.tool_support import run_with_client


def _order_amount(amount: dict[str, Any] | None) -> dict[str, Any] | None:
    if not amount:
        return None
    return {"currency_code": amount.get("currency_code"), "value": amount.get("value")}


def _order_body(
    currency: str,
    amount: str,
    description: str | None,
    items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    purchase_unit: dict[str, Any] = {"amount": {"currency_code": currency, "value": amount}}
    if description:
        purchase_unit["description"] = description
    if items:
        purchase_unit["items"] = items
    return {"intent": "CAPTURE", "purchase_units": [purchase_unit]}


def register(mcp, client_factory) -> None:
    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
    async def paypal_create_order(
        currency: str,
        amount: str,
        description: str | None = None,
        items: list[dict[str, Any]] | None = None,
        request_id: str | None = None,
    ) -> str:
        """Create a PayPal checkout order for a one-off payment.

        Args:
            currency: ISO 4217 currency code, e.g. "USD".
            amount: Decimal string total, e.g. "25.00".
            description: Optional line shown to the payer.
            items: Optional itemized cart (PayPal Orders v2 item objects); omit for a flat amount.
            request_id: Optional caller-chosen idempotency key; a retry with the same value
                returns the original order instead of creating a duplicate.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            body = _order_body(currency, amount, description, items)
            data = await client.request(
                "POST", "/v2/checkout/orders", json_body=body, idempotency_key=request_id
            )
            return {"id": data.get("id"), "status": data.get("status")}

        return await run_with_client(client_factory, _call, tool_name="paypal_create_order")

    @mcp.tool(annotations={"readOnlyHint": True})
    async def paypal_get_order(order_id: str) -> str:
        """Get a PayPal order's current status and amount.

        Args:
            order_id: The order id returned by paypal_create_order.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            data = await client.request("GET", f"/v2/checkout/orders/{order_id}")
            purchase_units = data.get("purchase_units") or [{}]
            return {
                "id": data.get("id"),
                "status": data.get("status"),
                "amount": _order_amount(purchase_units[0].get("amount")),
            }

        return await run_with_client(client_factory, _call, tool_name="paypal_get_order")

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False})
    async def paypal_capture_order(order_id: str) -> str:
        """Capture payment on an approved PayPal order. Irreversible once completed.

        Args:
            order_id: The id of an order in APPROVED status.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            data = await client.request("POST", f"/v2/checkout/orders/{order_id}/capture")
            purchase_units = data.get("purchase_units") or [{}]
            captures = (purchase_units[0].get("payments") or {}).get("captures") or [{}]
            capture = captures[0]
            return {
                "id": capture.get("id"),
                "status": capture.get("status"),
                "amount": _order_amount(capture.get("amount")),
            }

        return await run_with_client(client_factory, _call, tool_name="paypal_capture_order")
