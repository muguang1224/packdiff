"""Helpers for building throw-away directory trees in tests."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
from typing import Union

TreeSpec = dict[str, Union[str, bytes, None]]

#: ``None`` when git is unavailable, so tests can skip instead of failing.
GIT = shutil.which("git")

# Keep line endings out of the picture: a CRLF checkout would make every file
# look modified and turn git-based tests into flakes on Windows.
_GIT_SETTINGS = ("-c", "core.autocrlf=false", "-c", "core.safecrlf=false")
_GIT_IDENTITY = ("-c", "user.name=ctxpack tests", "-c", "user.email=tests@example.com")


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


def git_run(root: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in *root*, raising with git's own output when it fails."""
    proc = subprocess.run(
        ["git", *_GIT_SETTINGS, *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.decode()}")
    return proc


def git_commit(root: str, message: str) -> None:
    git_run(root, *_GIT_IDENTITY, "commit", "-q", "-m", message)


def init_repo(root: str) -> None:
    """Create a repository in *root* with everything currently there committed."""
    git_run(root, "init", "-q")
    git_run(root, "add", "-A")
    git_commit(root, "initial")


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
