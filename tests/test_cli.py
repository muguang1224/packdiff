"""End-to-end tests for the command-line interface."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from ctxpack.cli import _budget_for_files, build_parser, main, parse_size, parse_tokens
from ctxpack.tokens import estimate_tokens
from ctxpack.walk import PackedFile
from support import AsciiStream, make_tree


def run_cli(argv):
    """Run :func:`main` and capture ``(exit_code, stdout, stderr)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class QuantityParsingTests(unittest.TestCase):
    def test_token_suffixes_use_decimal_multipliers(self):
        self.assertEqual(parse_tokens("32k"), 32000)
        self.assertEqual(parse_tokens("1m"), 1000000)
        self.assertEqual(parse_tokens("512"), 512)

    def test_size_suffixes_use_binary_multipliers(self):
        self.assertEqual(parse_size("1k"), 1024)
        self.assertEqual(parse_size("2m"), 2 * 1024 * 1024)

    def test_bad_values_are_rejected(self):
        for value in ("", "abc", "12x", "0"):
            with self.assertRaises(argparse.ArgumentTypeError):
                parse_tokens(value)

    def test_budget_reserve_is_bounded(self):
        self.assertIsNone(_budget_for_files(None))
        self.assertGreater(_budget_for_files(100000), 95000)
        self.assertLessEqual(_budget_for_files(100000), 100000)


class CliBehaviourTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        make_tree(
            self.root,
            {
                "README.md": "# demo project\n",
                "src/app.py": "print('hello')\n",
                "src/util.py": "VALUE = 42\n",
                ".env": "TOKEN=secret\n",
                "assets/logo.png": b"\x89PNG\r\n\x1a\n",
            },
        )
        self.env = mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_parser_has_documented_flags(self):
        parser = build_parser()
        for flag in ("--max-tokens", "--include", "--exclude", "--list", "--no-tree", "--ascii"):
            self.assertIn(flag, parser.format_help())

    def test_help_lists_examples(self):
        self.assertIn("examples:", build_parser().format_help())

    def test_default_run_packs_the_tree_to_stdout(self):
        code, out, err = run_cli([self.root, "-q"])
        self.assertEqual(code, 0)
        self.assertIn("# ctxpack", out)
        self.assertIn("### `src/app.py`", out)
        self.assertIn("```python", out)
        self.assertEqual(err, "")

    def test_reproducible_output_with_source_date_epoch(self):
        first = run_cli([self.root, "-q"])[1]
        second = run_cli([self.root, "-q"])[1]
        self.assertEqual(first, second)
        self.assertIn("1970-01-01 00:00 UTC", first)

    def test_secret_file_is_excluded_and_reported(self):
        code, out, err = run_cli([self.root])
        self.assertEqual(code, 0)
        self.assertNotIn("TOKEN=secret", out)
        self.assertIn("Skipped as secret-like", out)
        self.assertIn("skipped .env", err)

    def test_include_secrets_flag_exposes_the_file(self):
        _, out, _ = run_cli([self.root, "-q", "--include-secrets"])
        self.assertIn("TOKEN=secret", out)

    def test_binary_asset_is_not_packed(self):
        _, out, _ = run_cli([self.root, "-q"])
        self.assertNotIn("logo.png", out)

    def test_output_flag_writes_a_file(self):
        target = os.path.join(self.root, "out", "context.md")
        code, out, err = run_cli([self.root, "-o", target, "-q"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(target))
        with open(target, encoding="utf-8") as handle:
            self.assertIn("# ctxpack", handle.read())
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_dash_output_means_stdout(self):
        code, out, _ = run_cli([self.root, "-q", "-o", "-"])
        self.assertEqual(code, 0)
        self.assertIn("# ctxpack", out)

    def test_max_tokens_defers_files(self):
        _, out, _ = run_cli([self.root, "-q", "--max-tokens", "50"])
        self.assertIn("Token budget: 50", out)

    def test_max_tokens_is_a_guarantee_on_the_rendered_document(self):
        make_tree(self.root, {f"src/mod{i}.py": "value = 1\n" * 120 for i in range(6)})
        for budget in (250, 600, 1800):
            _, out, _ = run_cli([self.root, "-q", "--max-tokens", str(budget)])
            measured = estimate_tokens(out)
            self.assertLessEqual(measured, budget, f"budget {budget}: measured {measured}")

    def test_shrinking_defers_the_least_valuable_file_first(self):
        make_tree(self.root, {"src/util.py": "x = 1\n" * 400})
        _, out, _ = run_cli([self.root, "-q", "--max-tokens", "400"])
        self.assertIn("## Deferred by token budget", out)
        # README is a priority file, so the big plain module goes instead.
        self.assertIn("README.md", out)

    def test_no_tree_flag_omits_the_tree(self):
        _, out, _ = run_cli([self.root, "-q", "--no-tree"])
        self.assertNotIn("## Directory tree", out)

    def test_ascii_flag_avoids_box_drawing(self):
        _, out, _ = run_cli([self.root, "-q", "--ascii"])
        self.assertIn("|-- ", out)
        self.assertNotIn("├──", out)

    def test_include_and_exclude_glob(self):
        _, out, _ = run_cli([self.root, "-q", "--include", "*.py"])
        self.assertIn("src/util.py", out)
        self.assertNotIn("README.md", out)

        _, out, _ = run_cli([self.root, "-q", "--exclude", "src/**"])
        self.assertNotIn("src/util.py", out)
        self.assertIn("# demo project", out)

    def test_list_mode_prints_a_table_without_content(self):
        code, out, _ = run_cli([self.root, "--list", "-q"])
        self.assertEqual(code, 0)
        self.assertIn("TOKENS", out)
        self.assertIn("src/app.py", out)
        self.assertNotIn("print('hello')", out)

    def test_missing_path_is_a_runtime_error(self):
        code, _, err = run_cli([os.path.join(self.root, "missing")])
        self.assertEqual(code, 1)
        self.assertIn("no such file or directory", err)

    def test_unknown_encoding_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli([self.root, "--encoding", "no-such-codec"])
        self.assertEqual(caught.exception.code, 2)

    def test_undecodable_tree_falls_back_to_ascii(self):
        stream = AsciiStream()
        with contextlib.redirect_stdout(stream):
            code = main([self.root, "-q"])
        self.assertEqual(code, 0)
        self.assertIn("|-- ", stream.getvalue())
        self.assertNotIn("├──", stream.getvalue())

    def test_nothing_to_pack_is_an_error(self):
        code, _, err = run_cli([self.root, "--include", "*.nope"])
        self.assertEqual(code, 1)
        self.assertIn("nothing to pack", err)

    def test_quiet_suppresses_the_summary(self):
        _, _, err = run_cli([self.root, "-q"])
        self.assertEqual(err, "")
        _, _, err = run_cli([self.root])
        self.assertIn("files,", err)

    def test_multiple_roots_are_merged_into_one_document(self):
        other = os.path.join(self.root, "docs")
        make_tree(self.root, {"docs/note.md": "note\n"})
        _, out, _ = run_cli([self.root, other, "-q"])
        self.assertIn(f"Roots: `{os.path.basename(self.root)}`, `docs`", out)
        self.assertIn("### Root `docs`", out)
        self.assertIn("note.md", out)


class BudgetSelectionTests(unittest.TestCase):
    def make(self, name, tokens, size, priority=1):
        return PackedFile(
            root="/repo",
            path=name,
            size=size,
            text="x",
            lines=1,
            language="python",
            tokens=tokens,
            priority=priority,
        )

    def test_no_budget_keeps_everything(self):
        from ctxpack.cli import select_within_budget

        files = [self.make("a.py", 10, 10), self.make("b.py", 10, 10)]
        selected, deferred = select_within_budget(files, None)
        self.assertEqual(len(selected), 2)
        self.assertEqual(deferred, [])

    def test_priority_files_win_over_larger_plain_files(self):
        from ctxpack.cli import select_within_budget

        readme = self.make("README.md", 30, 30, priority=0)
        big = self.make("big.py", 40, 100, priority=1)
        selected, deferred = select_within_budget([big, readme], 50)
        self.assertIn(readme, selected)
        self.assertEqual(deferred, [big])

    def test_deferred_files_are_sorted_by_path(self):
        from ctxpack.cli import select_within_budget

        files = [self.make("z.py", 10, 10), self.make("m.py", 10, 10), self.make("a.py", 10, 10)]
        selected, deferred = select_within_budget(files, 10)
        self.assertEqual([f.path for f in selected], ["a.py"])
        self.assertEqual([f.path for f in deferred], ["m.py", "z.py"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
