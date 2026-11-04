"""Async PayPal REST API client.

Request-scoped: a new PaypalClient is constructed per tool call from the
credentials in the current request context (app/context.py) and is never
reused or cached across requests (SOP S3.4; "Decisions made by DEV01" in
docs/tickets/PRD-21314.md -- token minted fresh per request, never cached).
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from typing import Any

import httpx

from app.errors import PaypalMcpError, map_paypal_status
from app.logging_utils import log_event
from app.settings import settings

_SANDBOX_HOST = "api-m.sandbox.paypal.com"
_LIVE_HOST = "api-m.paypal.com"

# Statuses worth retrying; everything else fails fast (SOP S5).
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class PaypalClient:
    """One PayPal REST API session for a single MCP tool call."""

    def __init__(self, client_id: str, client_secret: str, environment: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        # One id per tool call, used to correlate this client's log lines
        # (design doc S7 Observability: "trace id ... per request").
        self.trace_id = uuid.uuid4().hex[:12]
        base_url = _LIVE_HOST if environment == "live" else _SANDBOX_HOST
        self._base_url = f"https://{base_url}"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_seconds,
                read=settings.read_timeout_seconds,
                write=settings.read_timeout_seconds,
                pool=settings.read_timeout_seconds,
            ),
        )

    def _log(self, **fields: object) -> None:
        log_event(trace_id=self.trace_id, **fields)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "PaypalClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _mint_token(self) -> str:
        """POST /v1/oauth2/token. Minted fresh for this call, never cached (SOP S3.4)."""
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        try:
            resp = await self._http.post(
                "/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content="grant_type=client_credentials",
            )
        except httpx.HTTPError as exc:
            raise PaypalMcpError("upstream_error", f"PayPal token request failed: {exc}") from None

        if resp.status_code != 200:
            # Per the fixed error table, any token-mint failure is treated as
            # unauthorized -- a client credentials grant has no other failure
            # mode that matters to the caller (AC7). Never log the credential
            # headers or request body here (SOP S6, AC7).
            self._log(event="paypal_token_mint", status=resp.status_code, outcome="unauthorized")
            raise PaypalMcpError("unauthorized", "PayPal rejected the supplied credentials")

        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise PaypalMcpError("unauthorized", "PayPal token response had no access_token")
        return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Issue one PayPal REST call, with a fresh token and bounded retries (SOP S5, AC12)."""
        token = await self._mint_token()
        headers = {"Authorization": f"Bearer {token}"}
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key

        deadline = time.monotonic() + 120  # SOP S5: total call time, including retries, < 120s
        started = time.monotonic()
        attempt = 0
        last_error: PaypalMcpError | None = None

        while attempt <= settings.max_retries:
            if time.monotonic() >= deadline:
                break
            try:
                resp = await self._http.request(
                    method, path, headers=headers, json=json_body, params=params
                )
            except httpx.HTTPError as exc:
                last_error = PaypalMcpError("upstream_error", f"PayPal request failed: {exc}")
                self._log(event="paypal_api_call", method=method, path=path, outcome="network_error", attempt=attempt)
                attempt += 1
                await asyncio.sleep(min(2**attempt, 5))
                continue

            if resp.status_code < 300:
                self._log(
                    event="paypal_api_call", method=method, path=path, status=resp.status_code,
                    latency_ms=round((time.monotonic() - started) * 1000), attempt=attempt,
                )
                return {} if not resp.content else resp.json()

            debug_id = _debug_id(resp)
            if resp.status_code not in _RETRYABLE_STATUSES:
                self._log(
                    event="paypal_api_call", method=method, path=path, status=resp.status_code,
                    debug_id=debug_id, latency_ms=round((time.monotonic() - started) * 1000), attempt=attempt,
                )
                raise map_paypal_status(resp.status_code, _error_message(resp))

            last_error = map_paypal_status(resp.status_code, _error_message(resp))
            self._log(
                event="paypal_api_call", method=method, path=path, status=resp.status_code,
                debug_id=debug_id, outcome="retrying", attempt=attempt,
            )
            attempt += 1
            if attempt > settings.max_retries:
                break
            await asyncio.sleep(_retry_delay(resp, attempt))

        self._log(
            event="paypal_api_call", method=method, path=path, outcome="retry_budget_exhausted",
            latency_ms=round((time.monotonic() - started) * 1000), attempt=attempt,
        )
        raise last_error or PaypalMcpError("upstream_error", "PayPal request failed with no response")


def _debug_id(resp: httpx.Response) -> str | None:
    try:
        return resp.json().get("debug_id")
    except ValueError:
        return None


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"PayPal returned HTTP {resp.status_code}"
    name = body.get("name") or body.get("error")
    message = body.get("message") or body.get("error_description")
    debug_id = body.get("debug_id")
    parts = [p for p in (name, message) if p]
    text = ": ".join(parts) if parts else f"PayPal returned HTTP {resp.status_code}"
    return f"{text} (debug_id={debug_id})" if debug_id else text


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(2**attempt, 5)
