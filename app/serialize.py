"""Compact JSON serialization for tool results (SOP S2.5: no indent, no ASCII escaping)."""

from __future__ import annotations

import json
from typing import Any


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
