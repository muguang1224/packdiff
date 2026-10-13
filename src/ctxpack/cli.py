"""Command-line interface for ctxpack."""

from __future__ import annotations

import argparse
import codecs
import contextlib
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timezone

from . import __version__
from .ignore import GlobSet
from .render import render_document
from .tokens import DEFAULT_RATIO, estimate_tokens, format_tokens
from .walk import ScanOptions, ScanResult, collect, format_size

PROGRAM = "ctxpack"
HOMEPAGE = "https://github.com/muguang1224/ctxpack"

#: Share of the budget held back for the header, overview table and tree.
BUDGET_RESERVE_RATIO = 0.03
BUDGET_RESERVE_MIN = 120
BUDGET_RESERVE_MAX = 2000

EPILOG = """\
examples:
  ctxpack                             pack the current directory to stdout
  ctxpack . -o context.md             write the pack to a file
  ctxpack --max-tokens 32k -o ctx.md  fit the pack into ~32k tokens
  ctxpack --include '*.py' --exclude 'tests/**'
  ctxpack --list                      show what would be packed, without content
  ctxpack src/ tests/                 pack several roots in one document

ignore rules:
  .gitignore files (including nested ones) are honoured, unless --no-gitignore.
  Add a .ctxpackignore at the root for machine-local exclusions.
  --include/--exclude accept the same glob syntax, e.g. '!src/keep.py'.

exit status:
  0 success, 1 runtime error, 2 usage error.
"""


# ---------------------------------------------------------------------------
# argument parsing helpers
# ---------------------------------------------------------------------------

_SIZE_SUFFIXES = {"": 1, "b": 1, "k": 1024, "kb": 1024, "m": 1024**2, "mb": 1024**2, "g": 1024**3}
_COUNT_SUFFIXES = {"": 1, "k": 1000, "m": 1000000}


def _parse_quantity(text: str, suffixes, what: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*", text or "")
    if not match:
        raise argparse.ArgumentTypeError(f"invalid {what}: {text!r}")
    number, unit = match.group(1), match.group(2).lower()
    if unit not in suffixes:
        raise argparse.ArgumentTypeError(f"unknown unit {unit!r} in {what} {text!r}")
    value = int(float(number) * suffixes[unit])
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{what} must be positive")
    return value


def parse_size(text: str) -> int:
    """``'512k'`` -> ``524288`` (binary multipliers)."""
    return _parse_quantity(text, _SIZE_SUFFIXES, "size")


def parse_tokens(text: str) -> int:
    """``'32k'`` -> ``32000`` (decimal multipliers, as model context is stated)."""
    return _parse_quantity(text, _COUNT_SUFFIXES, "token budget")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Pack a repository into one Markdown file that is easy to paste into "
            "an LLM prompt: directory tree, language overview, and every text file "
            "in fenced code blocks."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="files or directories to pack (default: the current directory)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write the pack to FILE instead of stdout ('-' means stdout)",
    )
    parser.add_argument(
        "--max-tokens",
        type=parse_tokens,
        metavar="N",
        help="keep the pack under roughly N tokens (accepts 32k, 1m)",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="only pack paths matching this glob (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip paths matching this glob (repeatable)",
    )
    parser.add_argument(
        "--ignore-file",
        metavar="FILE",
        help="extra ignore file, gitignore syntax (default: .ctxpackignore if present)",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="do not read .gitignore / .git/info/exclude",
    )
    parser.add_argument(
        "--no-default-ignores",
        action="store_true",
        help="do not apply the built-in denylist (node_modules, dist, lockfiles, ...)",
    )
    parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="do not skip .env and key-like files (dangerous: the pack is meant to be shared)",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="descend into symlinked directories (loop-protected)",
    )
    parser.add_argument(
        "--max-file-size",
        type=parse_size,
        default=1024 * 1024,
        metavar="SIZE",
        help="skip text files larger than SIZE (default: 1m)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        metavar="ENC",
        help="text encoding to read files with (default: utf-8)",
    )
    parser.add_argument(
        "--token-ratio",
        type=float,
        default=DEFAULT_RATIO,
        metavar="R",
        help=f"characters per token for ASCII text (default: {DEFAULT_RATIO:g})",
    )
    parser.add_argument(
        "--no-tree", dest="tree", action="store_false", help="omit the directory tree"
    )
    parser.add_argument("--ascii", action="store_true", help="use ASCII tree characters")
    parser.add_argument(
        "--list", dest="list_only", action="store_true", help="list files without packing them"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress the stderr summary")
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    parser.set_defaults(tree=True)
    return parser


# ---------------------------------------------------------------------------
# budget selection
# ---------------------------------------------------------------------------


def select_within_budget(files: Sequence, max_tokens: int | None) -> tuple[list, list]:
    """Split *files* into ``(selected, deferred)`` respecting a token budget.

    Ordering is the interesting part, and it is a judgement call worth stating
    plainly.  Files whose *name* suggests architectural signal (README, package
    manifests, entry points) are admitted first.  Among the rest, the largest
    files go first, on the theory that a 400-line module tells you more about a
    codebase than a 3-line ``__init__.py`` — and small leftovers still squeeze
    into whatever budget is left.
    """
    ordered = list(files)
    if max_tokens is None:
        return ordered, []
    ordered.sort(key=lambda f: (f.priority, -f.size, f.path))
    selected, deferred, used = [], [], 0
    for packed in ordered:
        if used + packed.tokens <= max_tokens:
            selected.append(packed)
            used += packed.tokens
        else:
            deferred.append(packed)
    selected.sort(key=lambda f: f.path)
    deferred.sort(key=lambda f: f.path)
    return selected, deferred


def _budget_for_files(max_tokens: int | None) -> int | None:
    if max_tokens is None:
        return None
    reserve = int(max_tokens * BUDGET_RESERVE_RATIO)
    reserve = max(BUDGET_RESERVE_MIN, min(BUDGET_RESERVE_MAX, reserve))
    return max(0, max_tokens - reserve)


def _weakest(sections: Sequence[tuple[str, list]]):
    """Pick the file to drop next: lowest priority, then largest, then last by path."""
    best_key = None
    best = None
    for index, (_label, files) in enumerate(sections):
        for packed in files:
            key = (packed.priority, -packed.size, packed.path)
            if best_key is None or key > best_key:
                best_key, best = key, (index, packed)
    return best


def _shrink_to_budget(
    sections: list,
    deferred: list,
    document: str,
    max_tokens: int,
    ratio: float,
    render,
    limit: int = 25,
):
    """Drop the weakest admitted files until the *rendered* document fits.

    The per-file estimates used to build the selection cannot know how large the
    tree or the overview table will turn out to be, so the first pass is only a
    good guess. Measuring the finished document and deferring one file at a time
    turns ``--max-tokens`` into a guarantee rather than an aspiration; in
    practice one or two rounds are enough.
    """
    for _ in range(limit):
        if estimate_tokens(document, ratio) <= max_tokens:
            break
        victim = _weakest(sections)
        if victim is None:
            break
        index, packed = victim
        label, files = sections[index]
        sections = list(sections)
        sections[index] = (label, [item for item in files if item is not packed])
        deferred = [*deferred, packed]
        document = render(sections)

    return sections, deferred, document


# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------


def _stream_can_encode(stream, text: str) -> bool:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _emit(text: str, output: str | None, quiet: bool) -> None:
    if output and output != "-":
        target = os.path.abspath(output)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        if not quiet:
            print(f"wrote {target} ({format_size(len(text.encode('utf-8')))})", file=sys.stderr)
        return
    try:
        sys.stdout.write(text)
    except BrokenPipeError:  # pragma: no cover - e.g. `ctxpack . | head`
        # The interpreter flushes stdout at exit, which would raise again.
        with contextlib.suppress(OSError):
            sys.stdout.close()
        raise SystemExit(0) from None


def render_listing(results: Sequence[ScanResult], max_tokens: int | None) -> str:
    """Human-readable listing used by ``--list``."""
    lines = ["        TOKENS      SIZE  PATH", "        ------      ----  ----"]
    total_files = total_tokens = 0
    deferred_any = False
    for result in results:
        selected, deferred = select_within_budget(result.files, _budget_for_files(max_tokens))
        keep = {id(packed) for packed in selected}
        deferred_any = deferred_any or bool(deferred)
        if len(results) > 1:
            lines.append(f"  {result.label}/")
        for packed in result.files:
            total_files += 1
            total_tokens += packed.tokens
            marker = " " if id(packed) in keep else "~"
            note = "" if marker == " " else "  (deferred by budget)"
            lines.append(
                f"  {marker}  {format_tokens(packed.tokens):>8}  "
                f"{format_size(packed.size):>8}  {packed.path}{note}"
            )
    lines.append("")
    lines.append(f"  {total_files} files · ~{format_tokens(total_tokens)} tokens total")
    if deferred_any:
        lines.append("  (`~` marks files that a --max-tokens budget would defer)")
    return "\n".join(lines) + "\n"


def summarize(results: Sequence[ScanResult], quiet: bool) -> None:
    if quiet:
        return
    for result in results:
        if result.warning:
            print(f"{PROGRAM}: warning: {result.warning}", file=sys.stderr)
        counts = ", ".join(
            f"{value} {key}" for key, value in sorted(result.counts.items()) if value
        )
        detail = f" ({counts})" if counts else ""
        print(
            f"{PROGRAM}: {len(result.files)} files, {format_size(result.total_bytes)} "
            f"from {result.label}{detail}",
            file=sys.stderr,
        )
        for item in result.skipped:
            print(f"{PROGRAM}: skipped {item.path}: {item.reason}", file=sys.stderr)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def _resolve_generated_at() -> datetime:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except ValueError:  # pragma: no cover - defensive
            pass
    return datetime.now(timezone.utc)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.paths:
        args.paths = ["."]

    try:
        codecs.lookup(args.encoding)
    except LookupError:
        parser.error(f"unknown encoding: {args.encoding}")

    if args.token_ratio <= 0:
        parser.error("--token-ratio must be positive")

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        for path in missing:
            print(f"{PROGRAM}: error: no such file or directory: {path}", file=sys.stderr)
        return 1

    ignore_file = args.ignore_file
    if ignore_file is None:
        default_ignore = os.path.join(args.paths[0], ".ctxpackignore")
        if len(args.paths) == 1 and os.path.isfile(default_ignore):
            ignore_file = default_ignore
    elif not os.path.exists(ignore_file):
        print(f"{PROGRAM}: error: ignore file not found: {ignore_file}", file=sys.stderr)
        return 1

    options = ScanOptions(
        encoding=args.encoding,
        max_file_size=args.max_file_size,
        use_gitignore=not args.no_gitignore,
        default_ignores=not args.no_default_ignores,
        secret_filter=not args.include_secrets,
        follow_symlinks=args.follow_symlinks,
        include=GlobSet(args.include),
        exclude=GlobSet(args.exclude),
        ignore_file=ignore_file,
        token_ratio=args.token_ratio,
    )

    results, _labels = collect(args.paths, options)
    summarize(results, args.quiet)

    if not any(result.files for result in results):
        print(f"{PROGRAM}: error: nothing to pack (every candidate was filtered)", file=sys.stderr)
        return 1

    if args.list_only:
        _emit(render_listing(results, args.max_tokens), args.output, args.quiet)
        return 0

    payload_budget = _budget_for_files(args.max_tokens)
    sections: list[tuple[str, list]] = []
    deferred: list = []
    for result in results:
        if payload_budget is None:
            sections.append((result.label, list(result.files)))
            continue
        selected, skipped_by_budget = select_within_budget(result.files, payload_budget)
        payload_budget -= sum(f.tokens for f in selected)
        payload_budget = max(0, payload_budget)
        sections.append((result.label, selected))
        deferred.extend(skipped_by_budget)

    all_skipped = [item for result in results for item in result.skipped]

    tree_style = "ascii" if args.ascii else "unicode"
    if not args.ascii and not args.output and not _stream_can_encode(sys.stdout, "├── └── │"):
        tree_style = "ascii"
        if not args.quiet:
            print(
                f"{PROGRAM}: note: stdout encoding cannot render box-drawing characters; "
                "using an ASCII tree",
                file=sys.stderr,
            )

    generated_at = _resolve_generated_at()

    def render(selection):
        return render_document(
            sections=selection,
            version=__version__,
            generated_at=generated_at,
            omitted=deferred,
            skipped=all_skipped,
            show_tree=args.tree,
            tree_style=tree_style,
            max_tokens=args.max_tokens,
            token_ratio=args.token_ratio,
        )

    document = render(sections)
    if args.max_tokens is not None:
        sections, deferred, document = _shrink_to_budget(
            sections, deferred, document, args.max_tokens, args.token_ratio, render
        )

    _emit(document, args.output, args.quiet)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
