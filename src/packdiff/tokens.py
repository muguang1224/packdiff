"""Token estimation without a tokenizer.

Ship-time reality: nobody wants a 200 MB tokenizer wheel for a CLI whose whole
selling point is "no dependencies".  A calibrated heuristic gets within roughly
±10 % of BPE token counts for source code, which is more than good enough for
budgeting a prompt.

The estimator splits characters into two buckets:

* ASCII characters are charged at ``1 / ratio`` tokens each (default ratio 4 —
  the well-known "~4 characters per token" rule of thumb for English and code).
* Non-ASCII characters (CJK, emoji, accented text) are charged at one token
  each, because these are almost always a whole token or more under BPE.
"""

from __future__ import annotations

import math

__all__ = ["DEFAULT_RATIO", "estimate_tokens", "format_tokens"]

DEFAULT_RATIO = 4.0


def estimate_tokens(text: str, ratio: float = DEFAULT_RATIO) -> int:
    """Estimate the number of BPE tokens in *text*.

    >>> estimate_tokens("hello world")
    3
    >>> estimate_tokens("") == 0
    True
    """
    if not text:
        return 0
    if ratio <= 0:
        raise ValueError("ratio must be positive")
    try:
        ascii_only = len(text.encode("ascii", "ignore"))
    except (UnicodeError, LookupError):  # pragma: no cover - defensive
        ascii_only = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = len(text) - ascii_only
    return math.ceil(ascii_only / ratio) + non_ascii


def format_tokens(count: int) -> str:
    """Render a token count for humans: ``1_234`` -> ``1,234``."""
    return f"{count:,}"
