# Contributing

Thanks for taking the time. Issues and pull requests are both welcome.

## Getting set up

```bash
git clone https://github.com/muguang1224/ctxpack
cd ctxpack
python -m pip install -e ".[dev]"
```

## Before you open a pull request

```bash
python -m pytest               # all tests must pass
ruff check .                   # lint
ruff format --check .          # formatting
```

If your change alters the output format, update the sample in `README.md` and
add a line to the `Unreleased` section of `CHANGELOG.md`. If it changes what a
pack looks like, also run:

```bash
python3 examples/regenerate.py     # rebuild the committed example pack
```

`tests/test_examples.py` compares that committed pack byte for byte against a
fresh render, so it will fail until you do. That is the point: the example is a
golden file, and a golden file that drifts is worse than none.

## Checking the ignore engine against git

`.gitignore` semantics are full of corners — trailing `**`, directory-only
patterns, escapes, nested ignore files — so `ignore.py` has an oracle:

```bash
python3 tools/gitignore_oracle.py .        # or any repository you trust
```

It walks a real repository, asks `git check-ignore --no-index` about every path,
and reports any path where ctxpack disagrees. It is not part of the test suite
because it shells out to `git`, but please run it against a repository with
interesting ignore rules before changing `ignore.py`. The three subtlest rules
it caught during development are documented in `IgnorePattern.matches` — the
tests for them cite `git check-ignore` for that reason.

## What this project cares about

**Zero runtime dependencies.** ctxpack exists partly because a `pip install`
should not pull a dependency tree into someone's environment. A pull request that
adds a runtime dependency needs a strong argument.

**Nothing disappears silently.** If the tool skips a file, the reason is either
printed to stderr or written into the document. Features that quietly drop data
will be pushed back on.

**Honest documentation.** If a heuristic is approximate, say so where the user
will read it — that is why the token estimator's error bars are in the README.

**Small, focused modules.** `ignore.py` knows about gitignore semantics and
nothing else; `render.py` knows about Markdown and nothing else. Please keep it
that way.

## Testing style

Tests are plain `unittest` cases so they run with or without pytest, and they
build their fixtures in temporary directories using `tests/support.py`. No
network access, no committed fixtures, and they must pass on Windows — which
means no hard-coded `/` path separators and no assumptions about case-sensitive
filesystems.

The `--diff` tests create real repositories and shell out to git, so they are
skipped where git is not installed. `tests/support.py` passes
`core.autocrlf=false` to every git command on purpose; without it a CRLF
checkout makes every file look modified and the tests go flaky on Windows.

## Reporting a bug

Please include the version (`ctxpack --version`), your OS, the exact command,
and — if it is safe to share — the relevant part of `ctxpack --list` output.
Never paste a pack of a private repository into a public issue.
