"""Regenerate ``examples/demo-project.pack.md``.

The generated file is committed so that visitors can see ctxpack's output
without installing anything, and ``tests/test_examples.py`` asserts that the
committed copy still matches what the tool produces.  If you change the output
format, run this script and commit the result — the test will tell you if you
forget.

    python3 examples/regenerate.py
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "examples" / "demo-project"
OUTPUT = REPO_ROOT / "examples" / "demo-project.pack.md"

#: 2026-01-01T00:00:00Z — pinned so the header timestamp, and therefore the
#: committed file, does not change every time somebody regenerates it.
FIXED_EPOCH = "1767225600"

sys.path.insert(0, str(REPO_ROOT / "src"))

from ctxpack.cli import main  # noqa: E402  (imported after sys.path is extended)


def build_pack() -> str:
    """Render the demo pack exactly as the CLI would. Importable for tests."""
    buffer = io.StringIO()
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = FIXED_EPOCH
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(DEMO_DIR), "-q"])
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous
    if code != 0:
        raise SystemExit(f"ctxpack exited with {code} while packing the demo project")
    return buffer.getvalue()


def run() -> int:
    pack = build_pack()
    OUTPUT.write_text(pack, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(pack)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
