"""Tests for directory walking, filtering and decoding."""

from __future__ import annotations

import os
import tempfile
import unittest

from ctxpack.ignore import GlobSet
from ctxpack.walk import ScanOptions, format_size, scan_root
from support import make_tree, paths_of


class TreeMixin(unittest.TestCase):
    """Shared fixture: a small project with one of everything."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        make_tree(
            self.root,
            {
                ".gitignore": "*.log\nbuild/\n",
                "README.md": "# demo\n",
                "src/app.py": "print('hi')\n",
                "src/util.py": "VALUE = 1\n",
                "src/deep/mod.py": "def f():\n    return 2\n",
                "src/deep/notes.log": "noise\n",
                "build/out.txt": "generated\n",
                "docs/guide.md": "guide\n",
                "plugins/.gitignore": "*.py\n",
                "plugins/keep.py": "ignored by nested rule\n",
                "plugins/keep.txt": "kept\n",
                "node_modules/pkg/index.js": "module.exports = 1\n",
                "assets/logo.png": b"\x89PNG\r\n\x1a\n",
                "assets/blob.dat": b"text\x00binary\x01data",
                "empty.py": "",
                ".env": "SECRET=1\n",
                ".env.example": "SECRET=changeme\n",
            },
        )

    def scan(self, **overrides):
        options = ScanOptions(**overrides)
        options.include = overrides.get("include") or GlobSet()
        options.exclude = overrides.get("exclude") or GlobSet()
        return scan_root(self.root, options)


class DefaultScanTests(TreeMixin):
    def test_text_files_are_collected_and_noise_is_not(self):
        found = paths_of(self.scan())
        self.assertIn("README.md", found)
        self.assertIn("src/app.py", found)
        self.assertIn("src/deep/mod.py", found)
        self.assertIn("docs/guide.md", found)
        self.assertIn(".env.example", found)
        self.assertIn(".gitignore", found)

    def test_gitignore_rules_are_honoured(self):
        found = paths_of(self.scan())
        self.assertNotIn("src/deep/notes.log", found)
        self.assertNotIn("build/out.txt", found)

    def test_nested_gitignore_applies_only_below_itself(self):
        found = paths_of(self.scan())
        self.assertNotIn("plugins/keep.py", found)
        self.assertIn("plugins/keep.txt", found)
        self.assertIn("src/app.py", found)

    def test_built_in_denylist_excludes_dependency_trees(self):
        self.assertNotIn("node_modules/pkg/index.js", paths_of(self.scan()))

    def test_binary_files_are_dropped(self):
        found = paths_of(self.scan())
        self.assertNotIn("assets/logo.png", found)  # by extension
        self.assertNotIn("assets/blob.dat", found)  # by NUL sniff

    def test_secret_files_are_dropped_and_reported(self):
        result = self.scan()
        self.assertNotIn(".env", paths_of(result))
        reasons = {item.path: item.reason for item in result.skipped}
        self.assertIn(".env", reasons)
        self.assertIn("secret", reasons[".env"])

    def test_empty_file_is_skipped(self):
        self.assertNotIn("empty.py", paths_of(self.scan()))

    def test_language_and_line_metadata(self):
        files = {packed.path: packed for packed in self.scan().files}
        app = files["src/app.py"]
        self.assertEqual(app.language, "python")
        self.assertEqual(app.lines, 1)
        self.assertGreater(app.tokens, 0)


class OptionTests(TreeMixin):
    def test_include_globs_narrow_the_scan(self):
        found = paths_of(self.scan(include=GlobSet(["*.md"])))
        self.assertEqual(found, {"README.md", "docs/guide.md"})

    def test_exclude_globs_remove_paths(self):
        found = paths_of(self.scan(exclude=GlobSet(["docs/**"])))
        self.assertNotIn("docs/guide.md", found)
        self.assertIn("README.md", found)

    def test_include_secrets_flag_restores_secret_files(self):
        self.assertIn(".env", paths_of(self.scan(secret_filter=False)))

    def test_no_default_ignores_flag_restores_dependency_trees(self):
        self.assertIn("node_modules/pkg/index.js", paths_of(self.scan(default_ignores=False)))

    def test_no_gitignore_flag_restores_ignored_files(self):
        found = paths_of(self.scan(use_gitignore=False, default_ignores=False))
        self.assertIn("src/deep/notes.log", found)
        self.assertIn("build/out.txt", found)
        self.assertIn("plugins/keep.py", found)

    def test_the_two_ignore_switches_are_independent(self):
        # build/ is in the built-in denylist, so --no-gitignore alone is not enough.
        self.assertNotIn("build/out.txt", paths_of(self.scan(use_gitignore=False)))
        self.assertIn(
            "build/out.txt", paths_of(self.scan(use_gitignore=False, default_ignores=False))
        )

    def test_max_file_size_skips_large_files(self):
        make_tree(self.root, {"big.txt": "x" * 5000})
        result = self.scan(max_file_size=1024)
        self.assertNotIn("big.txt", paths_of(result))
        self.assertTrue(any("larger than" in item.reason for item in result.skipped))

    def test_crlf_is_normalised_to_lf(self):
        make_tree(self.root, {"crlf.txt": "line1\r\nline2\r\n"})
        files = {packed.path: packed for packed in self.scan().files}
        self.assertEqual(files["crlf.txt"].text, "line1\nline2\n")

    def test_custom_ignore_file_is_applied(self):
        ignore_path = os.path.join(self.root, "extra.ignore")
        with open(ignore_path, "w", encoding="utf-8") as handle:
            handle.write("*.md\n")
        found = paths_of(self.scan(ignore_file=ignore_path))
        self.assertNotIn("README.md", found)
        self.assertIn("src/app.py", found)

    def test_priority_files_are_marked(self):
        files = {packed.path: packed for packed in self.scan().files}
        self.assertEqual(files["README.md"].priority, 0)
        self.assertEqual(files["src/util.py"].priority, 1)


class SingleFileTests(unittest.TestCase):
    def test_a_lone_file_can_be_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "notes.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("hello\n")
            result = scan_root(path, ScanOptions())
            self.assertEqual([packed.path for packed in result.files], ["notes.md"])

    def test_empty_single_file_is_still_packed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.md")
            with open(path, "w", encoding="utf-8"):
                pass
            result = scan_root(path, ScanOptions())
            self.assertEqual(len(result.files), 1)


class MissingPathTests(unittest.TestCase):
    def test_missing_path_produces_a_warning_and_no_files(self):
        result = scan_root(os.path.join("nope", "nope"), ScanOptions())
        self.assertEqual(result.files, [])
        self.assertIsNotNone(result.warning)


class FormatSizeTests(unittest.TestCase):
    def test_human_readable(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(999), "999 B")
        self.assertEqual(format_size(2048), "2.0 KiB")
        self.assertEqual(format_size(1024 * 1024 * 3 // 2), "1.5 MiB")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
