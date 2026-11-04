"""PayPal Payments v2 tools: captures and refunds."""

from __future__ import annotations

from typing import Any

from app.paypal_client import PaypalClient
from app.tool_support import run_with_client


def _amount(data: dict[str, Any]) -> dict[str, Any] | None:
    amount = data.get("amount")
    if not amount:
        return None
    return {"currency_code": amount.get("currency_code"), "value": amount.get("value")}


def register(mcp, client_factory) -> None:
    @mcp.tool(annotations={"readOnlyHint": True})
    async def paypal_get_capture(capture_id: str) -> str:
        """Get a PayPal capture's current status and amount.

        Args:
            capture_id: The capture id returned by paypal_capture_order.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            data = await client.request("GET", f"/v2/payments/captures/{capture_id}")
            return {"id": data.get("id"), "status": data.get("status"), "amount": _amount(data)}

        return await run_with_client(client_factory, _call, tool_name="paypal_get_capture")

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False})
    async def paypal_refund_capture(
        capture_id: str,
        amount: str | None = None,
        currency: str | None = None,
        note_to_payer: str | None = None,
    ) -> str:
        """Refund a completed PayPal capture, fully or partially. Irreversible.

        Args:
            capture_id: The id of a capture in COMPLETED status.
            amount: Optional decimal string to refund partially; omit to refund in full.
            currency: Required alongside `amount` -- ISO 4217 currency code of the refund.
            note_to_payer: Optional note shown to the payer.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            body: dict[str, Any] = {}
            if amount:
                body["amount"] = {"currency_code": currency, "value": amount}
            if note_to_payer:
                body["note_to_payer"] = note_to_payer
            data = await client.request(
                "POST", f"/v2/payments/captures/{capture_id}/refund", json_body=body or None
            )
            return {"id": data.get("id"), "status": data.get("status")}

        return await run_with_client(client_factory, _call, tool_name="paypal_refund_capture")

    @mcp.tool(annotations={"readOnlyHint": True})
    async def paypal_get_refund(refund_id: str) -> str:
        """Get a PayPal refund's current status and amount.

        Args:
            refund_id: The refund id returned by paypal_refund_capture.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            data = await client.request("GET", f"/v2/payments/refunds/{refund_id}")
            return {"id": data.get("id"), "status": data.get("status"), "amount": _amount(data)}

        return await run_with_client(client_factory, _call, tool_name="paypal_get_refund")
