"""Helpers for building throw-away directory trees in tests."""

from __future__ import annotations

import io
import os
from typing import Union

TreeSpec = dict[str, Union[str, bytes, None]]


def make_tree(root: str, spec: TreeSpec) -> None:
    """Materialise *spec* under *root*.

    Keys are posix-ish relative paths.  Values are ``str`` (written as UTF-8),
    ``bytes`` (written raw, handy for binary-detection tests) or ``None`` to
    create a directory.
    """
    for rel, payload in spec.items():
        target = os.path.join(root, *rel.split("/"))
        if payload is None:
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        if isinstance(payload, bytes):
            with open(target, "wb") as handle:
                handle.write(payload)
        else:
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)


def paths_of(result) -> set:
    """Relative paths of every file a :class:`ScanResult` accepted."""
    return {packed.path for packed in result.files}


class AsciiStream:
    """A stdout stand-in that can only encode ASCII, for fallback tests."""

    encoding = "ascii"

    def __init__(self) -> None:
        self._buffer = io.StringIO()

    def write(self, text: str) -> int:
        return self._buffer.write(text)

    def flush(self) -> None:  # pragma: no cover - no buffering here
        pass

    def getvalue(self) -> str:
        return self._buffer.getvalue()
