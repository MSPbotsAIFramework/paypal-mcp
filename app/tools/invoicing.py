"""PayPal Invoicing v2 tools: create, send, get, list."""

from __future__ import annotations

from typing import Any

from app.paypal_client import PaypalClient
from app.tool_support import run_with_client

_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100  # PayPal's own page_size maximum (SOP S2.5, AC10).


def _invoice_body(recipient_email: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "primary_recipients": [{"billing_info": {"email_address": recipient_email}}],
        "items": items,
    }


def register(mcp, client_factory) -> None:
    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
    async def paypal_create_invoice(
        recipient_email: str,
        items: list[dict[str, Any]],
        request_id: str | None = None,
    ) -> str:
        """Create a draft PayPal invoice. Does not send it -- call paypal_send_invoice next.

        Args:
            recipient_email: Email address of the customer to bill.
            items: Line items, each a PayPal invoicing item object (name, quantity, unit_amount).
            request_id: Optional caller-chosen idempotency key; a retry with the same value
                returns the original invoice instead of creating a duplicate.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            body = _invoice_body(recipient_email, items)
            data = await client.request(
                "POST", "/v2/invoicing/invoices", json_body=body, idempotency_key=request_id
            )
            return {"id": data.get("id"), "status": data.get("status", "DRAFT")}

        return await run_with_client(client_factory, _call, tool_name="paypal_create_invoice")

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False})
    async def paypal_send_invoice(invoice_id: str) -> str:
        """Send a draft PayPal invoice to its recipient by email. Customer-facing, cannot be undone.

        Args:
            invoice_id: The id of a draft invoice, from paypal_create_invoice.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            await client.request("POST", f"/v2/invoicing/invoices/{invoice_id}/send")
            # PayPal's send endpoint itself returns no useful body; fetch the
            # invoice's post-send status so the caller sees the real result.
            data = await client.request("GET", f"/v2/invoicing/invoices/{invoice_id}")
            return {"id": data.get("id"), "status": data.get("status")}

        return await run_with_client(client_factory, _call, tool_name="paypal_send_invoice")

    @mcp.tool(annotations={"readOnlyHint": True})
    async def paypal_get_invoice(invoice_id: str) -> str:
        """Get a PayPal invoice's current status.

        Args:
            invoice_id: The invoice id returned by paypal_create_invoice.
        """

        async def _call(client: PaypalClient) -> dict[str, Any]:
            data = await client.request("GET", f"/v2/invoicing/invoices/{invoice_id}")
            return {"id": data.get("id"), "status": data.get("status")}

        return await run_with_client(client_factory, _call, tool_name="paypal_get_invoice")

    @mcp.tool(annotations={"readOnlyHint": True})
    async def paypal_list_invoices(limit: int = _DEFAULT_LIST_LIMIT) -> str:
        """List invoices on the connected PayPal account, newest first.

        Args:
            limit: Max invoices to return (default 20, hard cap 100). Never returns unbounded results.
        """
        page_size = max(1, min(limit, _MAX_LIST_LIMIT))

        async def _call(client: PaypalClient) -> dict[str, Any]:
            data = await client.request(
                "GET", "/v2/invoicing/invoices", params={"page_size": page_size}
            )
            raw_items = data.get("items") or []
            items = [{"id": i.get("id"), "status": i.get("status")} for i in raw_items]
            total_items = data.get("total_items")
            has_more = bool(total_items is not None and total_items > len(items))
            return {"items": items, "has_more": has_more}

        return await run_with_client(client_factory, _call, tool_name="paypal_list_invoices")
