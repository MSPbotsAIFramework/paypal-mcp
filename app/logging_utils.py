"""Structured, credential-free request logging (SOP S6; design doc S7 Observability).

Every log line is one JSON object. Never pass credential headers, access
tokens, or raw PayPal response bodies into these calls -- only identifiers
(tool name, HTTP status, debug_id, latency).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("paypal_mcp")


def log_event(**fields: object) -> None:
    logger.info(json.dumps(fields, ensure_ascii=False, separators=(",", ":"), default=str))
