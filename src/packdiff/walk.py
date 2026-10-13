"""Directory walking, filtering and file reading.

The walker is where most of packdiff's "does the right thing without being
asked" behaviour lives: nested ``.gitignore`` files, a built-in denylist for
build artefacts, binary detection by content *and* by extension, and a secret
filter that keeps live credentials out of your prompt.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field

from .ignore import GlobSet, IgnoreStack, default_ignore_rule, load_ignore_rule
from .languages import is_binary_extension, is_secret_name, language_for
from .tokens import DEFAULT_RATIO, estimate_tokens

__all__ = [
    "PackedFile",
    "ScanOptions",
    "ScanResult",
    "Skipped",
    "format_size",
    "scan_root",
]

#: Directories that are noise in almost every repository.
DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        "__pycache__",
        "node_modules",
        "bower_components",
        ".venv",
        "venv",
        "env",
        ".tox",
        ".nox",
        ".eggs",
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".pytype",
        ".hypothesis",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".parcel-cache",
        ".cache",
        "coverage",
        "htmlcov",
        ".terraform",
        "vendor",
        ".gradle",
        ".idea",
        "Pods",
        "DerivedData",
        ".DS_Store",
    }
)

#: Individual files that are noise in almost every repository.
DEFAULT_IGNORED_FILES = frozenset(
    {
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
        "bun.lockb",
        "composer.lock",
        "Gemfile.lock",
        "Cargo.lock",
        "go.sum",
    }
)

#: Files that carry the most signal about a project, kept when a budget bites.
PRIORITY_NAMES = frozenset(
    {
        "readme.md",
        "readme.rst",
        "readme.txt",
        "readme",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "package.json",
        "tsconfig.json",
        "cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "composer.json",
        "gemfile",
        "mix.exs",
        "cmakelists.txt",
        "makefile",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "index.ts",
        "index.js",
        "main.py",
        "main.go",
        "main.rs",
        "main.ts",
        "app.py",
        "cli.py",
        "__main__.py",
    }
)

BINARY_SNIFF_BYTES = 8192


def format_size(num_bytes: int) -> str:
    """Human-readable byte count (``1536`` -> ``1.5 KiB``)."""
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"  # pragma: no cover - unreachable


@dataclass
class PackedFile:
    """A text file that made it into the pack."""

    root: str
    path: str  # posix path relative to the root
    size: int
    text: str
    lines: int
    language: str | None
    tokens: int
    priority: int

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass
class Skipped:
    """A file or directory that was left out, and why."""

    path: str
    reason: str


@dataclass
class ScanOptions:
    """Everything the walker needs to know about the user's intent."""

    encoding: str = "utf-8"
    max_file_size: int = 1024 * 1024
    use_gitignore: bool = True
    default_ignores: bool = True
    secret_filter: bool = True
    follow_symlinks: bool = False
    include: GlobSet = field(default_factory=GlobSet)
    exclude: GlobSet = field(default_factory=GlobSet)
    ignore_file: str | None = None
    token_ratio: float = DEFAULT_RATIO
    extra_ignored_dirs: tuple[str, ...] = ()
    extra_ignored_files: tuple[str, ...] = ()
    #: When set, only these root-relative paths are considered (used by --diff).
    only_paths: frozenset[str] | None = None

    def ignored_dirs(self) -> set[str]:
        if not self.default_ignores:
            return set(self.extra_ignored_dirs)
        return set(DEFAULT_IGNORED_DIRS) | set(self.extra_ignored_dirs)

    def ignored_files(self) -> set[str]:
        if not self.default_ignores:
            return set(self.extra_ignored_files)
        return set(DEFAULT_IGNORED_FILES) | set(self.extra_ignored_files)

    def wanted_dirs(self) -> set[str]:
        """Directories worth descending into when ``only_paths`` is set."""
        if self.only_paths is None:
            return set()
        dirs: set[str] = set()
        for path in self.only_paths:
            parts = path.split("/")
            for depth in range(1, len(parts)):
                dirs.add("/".join(parts[:depth]))
        return dirs


@dataclass
class ScanResult:
    """The outcome of scanning one root."""

    root: str
    label: str
    files: list[PackedFile] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    warning: str | None = None

    def bump(self, key: str, amount: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + amount

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def total_tokens(self) -> int:
        return sum(f.tokens for f in self.files)


def _decode(data: bytes, encoding: str) -> str | None:
    """Decode *data* to text, or return ``None`` if it looks binary."""
    if b"\x00" in data[:BINARY_SNIFF_BYTES]:
        return None
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = data.decode(encoding, errors="replace")
        if not text:
            return None
        replacement_ratio = text.count("�") / len(text)
        if replacement_ratio > 0.02:
            return None
    if text.startswith("﻿"):
        text = text[1:]
    # Normalise line endings so the rendered pack is platform-independent.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _priority_for(name: str) -> int:
    lowered = name.lower()
    if lowered in PRIORITY_NAMES or lowered.startswith("readme"):
        return 0
    return 1


def _seed_ignores(root: str, options: ScanOptions) -> IgnoreStack:
    stack = IgnoreStack()
    if options.use_gitignore:
        stack.push(default_ignore_rule(root))
    if options.ignore_file:
        extra_path = options.ignore_file
        if os.path.isdir(extra_path):  # pragma: no cover - defensive
            extra_path = os.path.join(extra_path, ".packdiffignore")
        stack.push(load_ignore_rule(extra_path, base=""))
    return stack


def _read_text_file(path: str, options: ScanOptions) -> str | None:
    try:
        with open(path, "rb") as handle:
            data = handle.read(options.max_file_size + 1)
    except OSError:
        return None
    if len(data) > options.max_file_size:  # pragma: no cover - file grew mid-scan
        return None
    return _decode(data, options.encoding)


def scan_root(root: str, options: ScanOptions, label: str | None = None) -> ScanResult:
    """Scan a single file or directory tree and return what should be packed."""
    root = os.path.abspath(root)
    label = label or (os.path.basename(root.rstrip(os.sep)) or root)
    result = ScanResult(root=root, label=label)

    if os.path.isfile(root):
        name = os.path.basename(root)
        # With --diff a single-file root is filtered by its own name; see
        # git.paths_within, which reports exactly that for a file root.
        if options.only_paths is not None and name not in options.only_paths:
            return result
        _collect_file(root, name, root, options, result, skip_empty=False)
        return result

    if not os.path.isdir(root):
        result.warning = f"path does not exist: {root}"
        return result

    ignores = _seed_ignores(root, options)
    _walk(root, "", ignores, options, root, result, {os.path.realpath(root)}, options.wanted_dirs())
    result.files.sort(key=lambda f: f.path)
    return result


def _outside_change_set(
    rel: str, is_dir: bool, only_paths: frozenset[str], wanted_dirs: set[str]
) -> bool:
    """True when ``--diff`` should skip *rel*."""
    if rel in only_paths:
        return False
    return not (is_dir and rel in wanted_dirs)


def _walk(
    dir_abs: str,
    rel_prefix: str,
    ignores: IgnoreStack,
    options: ScanOptions,
    root: str,
    result: ScanResult,
    visited: set[str],
    wanted_dirs: set[str],
) -> None:
    try:
        entries = list(os.scandir(dir_abs))
    except OSError as exc:
        result.skipped.append(Skipped(rel_prefix or ".", f"unreadable directory ({exc.strerror})"))
        return

    pushed = 0
    if options.use_gitignore:
        candidate = os.path.join(dir_abs, ".gitignore")
        if os.path.isfile(candidate):
            ignores.push(load_ignore_rule(candidate, base=rel_prefix))
            pushed += 1

    ignored_dirs = options.ignored_dirs()
    ignored_files = options.ignored_files()

    entries.sort(key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower(), e.name))

    for entry in entries:
        name = entry.name
        rel = f"{rel_prefix}/{name}" if rel_prefix else name
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:  # pragma: no cover - broken symlink
            continue

        # --diff: a file must be in the change set, and a directory is only worth
        # entering when something in the change set lives underneath it.
        if options.only_paths is not None and _outside_change_set(
            rel, is_dir, options.only_paths, wanted_dirs
        ):
            continue

        is_link = entry.is_symlink()

        if is_dir:
            if name in ignored_dirs:
                continue
            if options.exclude and options.exclude.matches(rel, True):
                continue
            if ignores.is_ignored(rel, True):
                continue
            if is_link:
                if not options.follow_symlinks:
                    result.skipped.append(Skipped(rel, "symlinked directory"))
                    continue
                real = os.path.realpath(entry.path)
                if real in visited:
                    result.skipped.append(Skipped(rel, "symlink loop"))
                    continue
                visited.add(real)
            _walk(entry.path, rel, ignores, options, root, result, visited, wanted_dirs)
            continue

        if ignores.is_ignored(rel, False):
            continue
        if name in ignored_files:
            continue
        if options.exclude and options.exclude.matches(rel, False):
            continue
        if options.include and not options.include.matches(rel, False):
            continue
        _collect_file(entry.path, rel, root, options, result, skip_empty=True)

    for _ in range(pushed):
        ignores.pop()


def _collect_file(
    abspath: str,
    rel: str,
    root: str,
    options: ScanOptions,
    result: ScanResult,
    skip_empty: bool,
) -> None:
    name = os.path.basename(rel)

    if options.secret_filter and is_secret_name(name):
        result.skipped.append(Skipped(rel, "looks like a secret (pass --include-secrets)"))
        return

    if is_binary_extension(name):
        result.bump("binary")
        return

    try:
        size = os.path.getsize(abspath)
    except OSError as exc:  # pragma: no cover - race
        result.skipped.append(Skipped(rel, f"stat failed ({exc.strerror})"))
        return

    if size > options.max_file_size:
        result.skipped.append(Skipped(rel, f"larger than {format_size(options.max_file_size)}"))
        return

    text = _read_text_file(abspath, options)
    if text is None:
        result.bump("binary")
        return

    if skip_empty and not text.strip():
        result.bump("empty")
        return

    language = language_for(name)
    tokens = (
        estimate_tokens(text, options.token_ratio) + estimate_tokens(rel, options.token_ratio) + 8
    )

    result.files.append(
        PackedFile(
            root=root,
            path=rel,
            size=size,
            text=text,
            lines=len(text.splitlines()),
            language=language,
            tokens=tokens,
            priority=_priority_for(name),
        )
    )


def collect(
    paths: Sequence[str],
    options: ScanOptions,
    per_root: Sequence[ScanOptions] | None = None,
) -> tuple[list[ScanResult], list[str]]:
    """Scan several roots, de-duplicating identical basenames for display.

    *per_root* overrides the options for individual roots; ``--diff`` needs that
    because the changed-file set is relative to each root.
    """
    results: list[ScanResult] = []
    labels: list[str] = []
    for index, path in enumerate(paths):
        abspath = os.path.abspath(path)
        label = os.path.basename(abspath.rstrip(os.sep)) or abspath
        if label in labels:
            suffix = 2
            while f"{label} ({suffix})" in labels:
                suffix += 1
            label = f"{label} ({suffix})"
        labels.append(label)
        root_options = per_root[index] if per_root is not None else options
        results.append(scan_root(abspath, root_options, label=label))
    return results, labels
