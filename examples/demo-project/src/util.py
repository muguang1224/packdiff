"""Small helpers for the demo service."""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_TIMEOUT = 5.0


def load_config(path: str) -> dict[str, Any]:
    """Read a JSON config file, or return sensible defaults if it is missing."""
    if not os.path.exists(path):
        return {"timeout": DEFAULT_TIMEOUT, "retries": 3}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def backoff(attempt: int, base: float = 0.5) -> float:
    """Exponential backoff, capped so a bad day does not become a hang."""
    return min(base * (2**attempt), 30.0)
