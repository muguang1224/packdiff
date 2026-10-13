"""A small, honest implementation of ``.gitignore`` pattern semantics.

Git's ignore rules are subtle enough that it is worth being explicit about
what this module does and does not do.

Supported
---------
``#`` comments, blank lines, ``\\#`` / ``\\!`` escapes, backslash escapes
anywhere inside a pattern (``foo\\ bar``), unescaped trailing whitespace
stripping, ``!`` negation, trailing ``/`` (directory-only), leading ``/``
anchoring, patterns containing ``/`` anchoring to the ignore file's directory,
``*`` / ``?`` / ``[...]`` within a single path segment, and ``**`` as a whole
segment (``**/x``, ``x/**``, ``a/**/b``).

The two ``**`` forms differ, exactly as in gitignore(5): a ``**`` at the end of
a pattern matches everything *inside* a directory but not the directory itself,
while ``**`` followed by more pattern matches zero or more directories.

Deliberately not supported
--------------------------
"Re-including a file whose parent directory is excluded" — git explicitly
forbids it too, and this implementation matches that behaviour for free because
the walker prunes excluded directories instead of descending into them.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = [
    "GlobSet",
    "IgnorePattern",
    "IgnoreRule",
    "IgnoreStack",
    "load_ignore_rule",
    "parse_ignore_lines",
]


def _strip_trailing_spaces(line: str) -> str:
    """Drop trailing spaces unless they are backslash-escaped (gitignore rule)."""
    end = len(line)
    while end > 0 and line[end - 1] == " ":
        backslashes = 0
        idx = end - 2
        while idx >= 0 and line[idx] == "\\":
            backslashes += 1
            idx -= 1
        if backslashes % 2 == 1:
            break
        end -= 1
    return line[:end]


def _segment_regex(segment: str) -> str:
    """Translate one gitignore path segment into a regex source string.

    ``fnmatch`` would be shorter, but it treats ``\\`` as an ordinary character,
    and git uses it to escape the next character (``foo\\ bar`` matches the file
    called ``foo bar``).  Writing the translation by hand also lets ``*`` and
    ``?`` stop at path separators, which fnmatch does not do.
    """
    out: list[str] = []
    index = 0
    length = len(segment)
    while index < length:
        char = segment[index]
        if char == "\\" and index + 1 < length:
            out.append(re.escape(segment[index + 1]))
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            end = index + 1
            if end < length and segment[end] in "!^":
                end += 1
            if end < length and segment[end] == "]":
                end += 1
            while end < length and segment[end] != "]":
                end += 1
            if end >= length:  # unterminated class: a literal '['
                out.append(re.escape("["))
                index += 1
            else:
                body = segment[index + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                index = end + 1
        else:
            out.append(re.escape(char))
            index += 1
    return "".join(out)


def _match_segments(
    path: Sequence[str], pattern: Sequence[str], regexes: Sequence[re.Pattern[str]]
) -> bool:
    """Recursive matcher over path segments, with gitignore's ``**`` semantics."""
    if not pattern:
        return not path
    head, rest = pattern[0], pattern[1:]
    regex_rest = regexes[1:]
    if head == "**":
        # A trailing ``**`` matches what is *inside* a directory, not the
        # directory itself; anywhere else it matches zero or more directories.
        minimum = 1 if not rest else 0
        return any(
            _match_segments(path[cut:], rest, regex_rest) for cut in range(minimum, len(path) + 1)
        )
    if not path:
        return False
    if not regexes[0].fullmatch(path[0]):
        return False
    return _match_segments(path[1:], rest, regex_rest)


@dataclass(frozen=True)
class IgnorePattern:
    """One parsed ignore line."""

    pattern: str
    negated: bool = False
    dir_only: bool = False
    anchored: bool = False
    segments: tuple[str, ...] = ()
    regexes: tuple[re.Pattern[str], ...] = ()

    def __post_init__(self) -> None:
        if self.segments and not self.regexes:
            object.__setattr__(
                self,
                "regexes",
                tuple(re.compile(_segment_regex(part)) for part in self.segments),
            )

    def matches(self, rel_path: str, is_dir: bool = False) -> bool:
        """Test *rel_path* (posix, relative to the ignore file's directory).

        Two rules from gitignore(5) are at play here, and both were checked
        against ``git check-ignore --no-index`` while this was written:

        * a directory-only pattern (``build/``) matches directories but not a
          *file* of the same name;
        * any pattern that matches a directory excludes everything inside it —
          ``docs/*`` ignores ``docs/deep/note.md`` because it ignores
          ``docs/deep`` first.
        """
        parts = tuple(p for p in rel_path.split("/") if p)
        if not parts:
            return False

        if self._match(parts) and (is_dir or not self.dir_only):
            return True
        # Every proper ancestor of a path is a directory, so a directory-only
        # pattern is satisfied by them unconditionally.
        return any(self._match(parts[:cut]) for cut in range(1, len(parts)))

    def _match(self, parts: Sequence[str]) -> bool:
        if not self.regexes:
            return False
        if not self.anchored:
            # A pattern with no slash matches the basename at any depth.
            return bool(parts) and bool(self.regexes[0].fullmatch(parts[-1]))
        return _match_segments(parts, self.segments, self.regexes)


def parse_ignore_lines(lines: Iterable[str]) -> list[IgnorePattern]:
    """Parse raw ignore-file lines into :class:`IgnorePattern` objects."""
    patterns: list[IgnorePattern] = []
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("\\#"):
            line = line[1:]
        line = _strip_trailing_spaces(line)
        if not line:
            continue

        negated = False
        if line.startswith("!"):
            negated = True
            line = line[1:]
        elif line.startswith("\\!"):
            line = line[1:]
        if not line:
            continue

        dir_only = line.endswith("/")
        if dir_only:
            line = line.rstrip("/")
        anchored = line.startswith("/") or "/" in line
        line = line.lstrip("/")
        if not line:
            continue

        patterns.append(
            IgnorePattern(
                pattern=line,
                negated=negated,
                dir_only=dir_only,
                anchored=anchored,
                segments=tuple(line.split("/")),
            )
        )
    return patterns


@dataclass
class IgnoreRule:
    """The patterns of a single ignore file, anchored at ``base``."""

    base: str  # posix path of the directory holding the ignore file, "" for root
    patterns: list[IgnorePattern]
    source: str = ""

    def relative(self, rel_path: str):
        """Return *rel_path* expressed relative to this rule's base, or None."""
        if not self.base:
            return rel_path
        if rel_path == self.base:
            return None
        prefix = self.base + "/"
        if rel_path.startswith(prefix):
            return rel_path[len(prefix) :]
        return None

    def decision(self, rel_path: str, is_dir: bool) -> bool | None:
        """``True`` = ignored, ``False`` = explicitly re-included, ``None`` = no match.

        Within a single ignore file the last matching pattern wins, which is
        how ``!`` negation is able to override an earlier exclusion.
        """
        sub = self.relative(rel_path)
        if sub is None:
            return None
        matched = False
        decision = False
        for pattern in self.patterns:
            if pattern.matches(sub, is_dir):
                matched = True
                decision = not pattern.negated
        return decision if matched else None

    def is_ignored(self, rel_path: str, is_dir: bool) -> bool:
        return self.decision(rel_path, is_dir) is True


def load_ignore_rule(path: str, base: str) -> IgnoreRule:
    """Read *path* and return its :class:`IgnoreRule` (missing file -> empty)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        lines = []
    return IgnoreRule(base=base, patterns=parse_ignore_lines(lines), source=path)


class IgnoreStack:
    """An ordered stack of ignore rules, outermost first."""

    def __init__(self, rules: Sequence[IgnoreRule] = ()) -> None:
        self._rules: list[IgnoreRule] = list(rules)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._rules)

    def push(self, rule: IgnoreRule) -> None:
        self._rules.append(rule)

    def pop(self) -> IgnoreRule:
        return self._rules.pop()

    def copy(self) -> IgnoreStack:
        return IgnoreStack(self._rules)

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Last matching pattern wins; deeper ignore files override shallower ones."""
        decision = False
        for rule in self._rules:
            verdict = rule.decision(rel_path, is_dir)
            if verdict is not None:
                decision = verdict
        return decision


class GlobSet:
    """A set of include/exclude globs supplied on the command line."""

    def __init__(self, patterns: Sequence[str] = ()) -> None:
        self._patterns = parse_ignore_lines(patterns)

    def __bool__(self) -> bool:
        return bool(self._patterns)

    def matches(self, rel_path: str, is_dir: bool = False) -> bool:
        hit = False
        for pattern in self._patterns:
            if pattern.matches(rel_path, is_dir):
                hit = not pattern.negated
        return hit


def default_ignore_rule(root: str) -> IgnoreRule:
    """``.git/info/exclude`` — repo-local excludes that are not committed."""
    path = os.path.join(root, ".git", "info", "exclude")
    if not os.path.isfile(path):
        return IgnoreRule(base="", patterns=[], source=path)
    return load_ignore_rule(path, base="")
