"""Structured error envelope and the fixed error-code vocabulary (SOP S4.2).

Tools never raise bare exceptions back through tools/call; every failure
path returns `PaypalMcpError.to_json()` as the tool's string result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

ErrorCode = Literal[
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
]

# code -> retryable, per the SOP's fixed vocabulary (S4.2).
_RETRYABLE: dict[ErrorCode, bool] = {
    "not_configured": False,
    "unauthorized": False,
    "not_found": False,
    "invalid_argument": False,
    "rate_limited": True,
    "upstream_error": True,
}


@dataclass
class PaypalMcpError(Exception):
    code: ErrorCode
    message: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "retryable": _RETRYABLE[self.code],
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def map_paypal_status(status_code: int, message: str) -> PaypalMcpError:
    """Map a PayPal HTTP status code to the fixed error vocabulary (SOP S4.2, AC5/AC7)."""
    if status_code == 404:
        return PaypalMcpError("not_found", message)
    if status_code in (401, 403):
        return PaypalMcpError("unauthorized", message)
    if status_code in (400, 422):
        return PaypalMcpError("invalid_argument", message)
    if status_code == 429:
        return PaypalMcpError("rate_limited", message)
    return PaypalMcpError("upstream_error", message)
