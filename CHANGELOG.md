# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-13

### Added

- `--diff [REV]` packs only the files that changed against a revision, defaulting
  to `HEAD` and including untracked files. It answers the most common question
  this tool gets asked — "show the model what I just changed" — without spending
  the context window on the rest of the repository. It works for a single file
  root (`ctxpack app.py --diff`) as well as for a tree. Change detection shells
  out to `git diff` so it agrees with what `git status` just told you, falls back
  to the empty tree in a repository with no commits yet, and reports a missing
  git, a bad revision or a path outside the repository as a clear error.
- `examples/` with a small demo project and its committed pack output, so the
  format can be inspected without installing anything. `examples/regenerate.py`
  rebuilds it and `tests/test_examples.py` fails if the committed copy goes
  stale, which keeps the two from drifting apart.
- CI now smoke-tests `--diff` in a scratch repository on every platform.
- The test suite is now 149 tests. The `--diff` work added integration tests
  that build real repositories in temporary directories, so they skip cleanly
  where git is not installed.

## [0.1.0] - 2026-10-13

First release.

### Added

- `ctxpack` CLI: pack one or more roots into a single Markdown document with a
  metadata header, language overview, directory tree and fenced file sections.
- `.gitignore` support, including nested ignore files anchored to their own
  directory, plus `.git/info/exclude` and an optional `.ctxpackignore`. The
  engine handles backslash escapes inside patterns, `**` as a whole segment with
  gitignore's trailing-`**` rule, and the rule that a pattern matching a
  directory excludes everything inside it. It was verified path-by-path against
  `git check-ignore --no-index` over more than a thousand paths spanning four
  real repositories and a synthetic edge-case corpus, with zero disagreements;
  the harness ships as `tools/gitignore_oracle.py`.
- Built-in denylist for build artefacts, dependency trees and lockfiles.
- Binary detection by extension and by content sniffing, with an encoding-aware
  decoder that rejects files that do not decode cleanly.
- Secret filter that skips `.env`, `*.pem`, `*.key`, `id_rsa`, `.netrc`,
  `credentials.json` and friends, while keeping `.env.example` style templates.
- `--max-tokens` budget with a documented admission order and an explicit
  "Deferred by token budget" section instead of silent truncation. The finished
  document is measured and shrunk until it fits, so the flag is a guarantee on
  the rendered output rather than an estimate.
- `--include` / `--exclude` globs using the same engine as `.gitignore`.
- `--list` mode to inspect token and byte costs without generating a pack.
- Dependency-free token estimator that handles CJK text without a tokenizer.
- `SOURCE_DATE_EPOCH` support for reproducible output.
- Unicode tree with an automatic ASCII fallback for streams that cannot encode
  box-drawing characters.
- Test suite of 108 tests covering the ignore engine, the walker, the renderer
  and the CLI end to end, including a test that `--max-tokens` is never
  exceeded by the rendered document.

[Unreleased]: https://github.com/muguang1224/ctxpack/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/muguang1224/ctxpack/releases/tag/v0.2.0
[0.1.0]: https://github.com/muguang1224/ctxpack/releases/tag/v0.1.0
