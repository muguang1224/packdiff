"""Git integration — used only by ``--diff``.

``--diff`` exists because "show the model what I just changed" is the most
common way to use this tool, and packing a whole repository for a three-file
change wastes most of the context window.

Shelling out to ``git`` (rather than reimplementing index parsing) keeps the
package dependency-free and, more importantly, means the answer matches what
``git status`` told the user a second earlier.
"""

from __future__ import annotations

import os
import subprocess

__all__ = [
    "EMPTY_TREE",
    "GitError",
    "changed_paths",
    "is_inside",
    "paths_within",
    "repo_root",
]

#: The hash git uses for "no commits yet"; diffing against it means "everything
#: currently in the working tree is new".
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class GitError(RuntimeError):
    """A git invocation failed in a way the user needs to know about."""


def _run_git(args: list[str], cwd: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise GitError("git was not found on PATH; --diff needs git installed") from exc
    if proc.returncode != 0:
        raise GitError(_first_error_line(proc.stderr) or f"git {' '.join(args)} failed")
    return proc.stdout


def _first_error_line(stderr: bytes) -> str:
    for raw in stderr.decode("utf-8", "replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("usage:"):
            continue
        return line.removeprefix("fatal: ").removeprefix("error: ")
    return ""


def _split_z(blob: bytes) -> list[str]:
    return [part for part in blob.decode("utf-8", "surrogateescape").split("\0") if part]


def repo_root(path: str = ".") -> str:
    """Absolute path of the enclosing repository's top level."""
    target = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    out = _run_git(["rev-parse", "--show-toplevel"], target or ".")
    return os.path.realpath(out.decode("utf-8", "surrogateescape").strip())


def _base_revision(revision: str, root: str) -> str:
    if revision != "HEAD":
        return revision
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        # A repository with no commits yet: everything is a change.
        return EMPTY_TREE
    return revision


def changed_paths(revision: str = "HEAD", cwd: str = ".") -> tuple[str, set[str]]:
    """Paths that differ between *revision* and the working tree.

    Returns ``(repo_root, paths)`` where *paths* are posix paths relative to the
    repository root.  Untracked files are included, because a new file is part
    of the change; deleted files are included too and simply fail to match
    anything on disk later.
    """
    root = repo_root(cwd)
    base = _base_revision(revision, root)
    # --no-renames keeps the output a plain list of existing/removed paths
    # instead of rename pairs, which is what a file-level filter wants.
    tracked = _run_git(["diff", "--name-only", "--no-renames", "-z", base], root)
    untracked = _run_git(["ls-files", "--others", "--exclude-standard", "-z"], root)
    return root, set(_split_z(tracked)) | set(_split_z(untracked))


def is_inside(root: str, repo: str) -> bool:
    """True when *root* is the repository root or a directory inside it."""
    real_root = os.path.realpath(root)
    return real_root == repo or real_root.startswith(os.path.join(repo, ""))


def paths_within(root: str, repo: str, paths: set[str]) -> set[str]:
    """Re-express repo-relative *paths* relative to *root*.

    Paths outside *root* are dropped, so ``ctxpack src --diff`` packs only the
    changed files that live under ``src``.
    """
    real_root = os.path.realpath(root)
    if real_root == repo:
        return set(paths)
    prefix = os.path.relpath(real_root, repo).replace(os.sep, "/") + "/"
    return {path[len(prefix) :] for path in paths if path.startswith(prefix)}
