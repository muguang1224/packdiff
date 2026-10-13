"""Independent verification: compare packdiff's ignore engine with real git.

Not part of the test suite (it shells out to `git`), just a one-off harness
used while developing the ignore engine.  Run it with:

    python3 tools/gitignore_oracle.py /path/to/repo

Every path in the repository is tested with `git check-ignore --no-index`, and
the same path is offered to a packdiff IgnoreStack built exactly the way the
walker builds it (root rules, then rules pushed as directories are entered).
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from packdiff.ignore import IgnoreStack, load_ignore_rule


def collect(root: str):
    """Yield ``(rel_path, is_dir, verdict)`` for every path, pruning nothing.

    The walker prunes ignored directories, but the oracle deliberately descends
    into them anyway so that the "a matched directory excludes its contents"
    rule is exercised too.
    """
    out = []

    def descend(base: str, stack: IgnoreStack) -> None:
        abs_dir = os.path.join(root, *base.split("/")) if base else root
        pushed = 0
        ignore_file = os.path.join(abs_dir, ".gitignore")
        if os.path.isfile(ignore_file):
            stack.push(load_ignore_rule(ignore_file, base=base))
            pushed += 1
        try:
            entries = sorted(os.listdir(abs_dir))
        except OSError:
            entries = []
        for name in entries:
            if name == ".git":
                continue
            rel = f"{base}/{name}" if base else name
            full = os.path.join(abs_dir, name)
            is_dir = os.path.isdir(full) and not os.path.islink(full)
            out.append((rel, is_dir, stack.is_ignored(rel, is_dir)))
            if is_dir:
                descend(rel, stack)
        for _ in range(pushed):
            stack.pop()

    descend("", IgnoreStack())
    return out


def main(root: str) -> int:
    checked = mismatches = 0
    for rel, is_dir, mine in collect(root):
        checked += 1
        git_says = (
            subprocess.run(
                ["git", "check-ignore", "-q", "--no-index", "--", rel],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        if git_says != mine:
            mismatches += 1
            print(f"MISMATCH {rel!r} dir={is_dir} git={git_says} packdiff={mine}")
    print(f"compared {checked} paths: {mismatches} mismatches")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")))
