"""Tests for the .gitignore pattern engine."""

from __future__ import annotations

import os
import tempfile
import unittest

from packdiff.ignore import (
    GlobSet,
    IgnoreRule,
    IgnoreStack,
    load_ignore_rule,
    parse_ignore_lines,
)


def one(line: str):
    patterns = parse_ignore_lines([line])
    assert len(patterns) == 1, f"expected exactly one pattern from {line!r}"
    return patterns[0]


class ParseTests(unittest.TestCase):
    def test_blank_and_comment_lines_are_dropped(self):
        self.assertEqual(parse_ignore_lines(["", "   ", "# note", "\n"]), [])

    def test_escaped_hash_is_a_literal(self):
        self.assertEqual(one("\\#tag").pattern, "#tag")
        self.assertFalse(one("\\#tag").negated)

    def test_negation_and_escape(self):
        pattern = one("!keep.py")
        self.assertTrue(pattern.negated)
        self.assertEqual(pattern.pattern, "keep.py")
        self.assertFalse(one("\\!literal").negated)
        self.assertEqual(one("\\!literal").pattern, "!literal")

    def test_directory_only_and_anchoring(self):
        directory = one("build/")
        self.assertTrue(directory.dir_only)
        self.assertFalse(directory.anchored)
        self.assertTrue(one("/build").anchored)
        self.assertTrue(one("src/generated").anchored)
        self.assertFalse(one("*.log").anchored)

    def test_trailing_spaces_are_stripped_unless_escaped(self):
        self.assertEqual(one("foo   ").pattern, "foo")
        self.assertEqual(one("foo\\ ").pattern, "foo\\ ")


class MatchTests(unittest.TestCase):
    def test_basename_pattern_matches_at_any_depth(self):
        pattern = one("*.pyc")
        self.assertTrue(pattern.matches("module.pyc"))
        self.assertTrue(pattern.matches("a/b/c/module.pyc"))
        self.assertFalse(pattern.matches("module.py"))

    def test_anchored_pattern_only_matches_from_the_root(self):
        pattern = one("src/generated")
        self.assertTrue(pattern.matches("src/generated", is_dir=True))
        self.assertFalse(pattern.matches("deep/src/generated", is_dir=True))

    def test_a_matched_directory_excludes_its_contents(self):
        # Verified against `git check-ignore --no-index`.
        self.assertTrue(one("src/generated").matches("src/generated/x.py"))
        self.assertTrue(one("deep/**/target").matches("deep/target/f.txt"))
        self.assertTrue(one("deep/**/target").matches("deep/x/target/f.txt"))
        # `docs/*` matches the directory `docs/deep`, so its contents go too.
        self.assertTrue(one("docs/*").matches("docs/deep"))
        self.assertTrue(one("docs/*").matches("docs/deep/note.md"))

    def test_directory_only_pattern_excludes_contents(self):
        pattern = one("build/")
        self.assertTrue(pattern.matches("build", is_dir=True))
        self.assertTrue(pattern.matches("build/out.txt", is_dir=False))
        self.assertTrue(pattern.matches("pkg/build/out.txt", is_dir=False))
        # A *file* named build is not excluded by a directory-only pattern.
        self.assertFalse(pattern.matches("build", is_dir=False))

    def test_double_star_patterns(self):
        self.assertTrue(one("**/logs").matches("a/b/logs", is_dir=True))
        self.assertTrue(one("**/logs").matches("logs", is_dir=True))
        self.assertTrue(one("src/**").matches("src/a/b.py"))
        self.assertTrue(one("a/**/z.py").matches("a/z.py"))
        self.assertTrue(one("a/**/z.py").matches("a/b/c/z.py"))
        self.assertFalse(one("a/**/z.py").matches("b/z.py"))

    def test_trailing_double_star_excludes_contents_not_the_directory(self):
        # gitignore(5): "a/**" matches everything inside a, not a itself.
        pattern = one("pkg/vendor/**")
        self.assertFalse(pattern.matches("pkg/vendor", is_dir=True))
        self.assertTrue(pattern.matches("pkg/vendor/lib.js"))
        self.assertTrue(pattern.matches("pkg/vendor/deep/lib.js"))

    def test_backslash_escapes_inside_a_pattern(self):
        # git uses "\" to escape the next character, so "foo\ bar" matches "foo bar".
        self.assertTrue(one("foo\\ bar.txt").matches("foo bar.txt"))
        self.assertFalse(one("foo\\ bar.txt").matches("fooXbar.txt"))
        self.assertTrue(one("\\*.log").matches("*.log"))
        self.assertFalse(one("\\*.log").matches("app.log"))

    def test_unterminated_character_class_is_literal(self):
        self.assertTrue(one("weird[.txt").matches("weird[.txt"))
        self.assertFalse(one("weird[.txt").matches("weirdi.txt"))

    def test_character_classes_and_question_mark(self):
        self.assertTrue(one("data[0-9].csv").matches("data3.csv"))
        self.assertFalse(one("data[0-9].csv").matches("dataX.csv"))
        self.assertTrue(one("v?.md").matches("v1.md"))
        self.assertTrue(one("v[!0-9].md").matches("vx.md"))
        self.assertFalse(one("v[!0-9].md").matches("v7.md"))
        self.assertTrue(one("[!a]b.txt").matches("zb.txt"))

    def test_star_does_not_cross_a_path_separator(self):
        self.assertFalse(one("docs/*.tmp").matches("docs/sub/note.tmp"))
        self.assertTrue(one("docs/*.tmp").matches("docs/note.tmp"))


class RuleTests(unittest.TestCase):
    def test_negation_overrides_earlier_pattern(self):
        rule = IgnoreRule(base="", patterns=parse_ignore_lines(["*.log", "!important.log"]))
        self.assertTrue(rule.is_ignored("debug.log", False))
        self.assertFalse(rule.is_ignored("important.log", False))

    def test_rule_anchored_at_subdirectory(self):
        rule = IgnoreRule(base="docs", patterns=parse_ignore_lines(["*.tmp"]))
        self.assertTrue(rule.is_ignored("docs/notes.tmp", False))
        self.assertFalse(rule.is_ignored("other/notes.tmp", False))

    def test_decision_returns_none_without_a_match(self):
        rule = IgnoreRule(base="", patterns=parse_ignore_lines(["*.log"]))
        self.assertIsNone(rule.decision("readme.md", False))


class StackTests(unittest.TestCase):
    def test_deeper_rule_wins(self):
        stack = IgnoreStack()
        stack.push(IgnoreRule(base="", patterns=parse_ignore_lines(["*.py"])))
        stack.push(IgnoreRule(base="vendor", patterns=parse_ignore_lines(["!*.py"])))
        self.assertTrue(stack.is_ignored("app.py", False))
        self.assertFalse(stack.is_ignored("vendor/app.py", False))

    def test_push_and_pop_restore_state(self):
        stack = IgnoreStack()
        self.assertFalse(stack.is_ignored("a.tmp", False))
        stack.push(IgnoreRule(base="", patterns=parse_ignore_lines(["*.tmp"])))
        self.assertTrue(stack.is_ignored("a.tmp", False))
        stack.pop()
        self.assertFalse(stack.is_ignored("a.tmp", False))


class LoadTests(unittest.TestCase):
    def test_load_ignore_rule_reads_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".gitignore")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("*.log\nbuild/\n")
            rule = load_ignore_rule(path, base="")
            self.assertTrue(rule.is_ignored("x.log", False))
            self.assertTrue(rule.is_ignored("build/thing", False))
            self.assertEqual(rule.source, path)

    def test_missing_file_yields_empty_rule(self):
        rule = load_ignore_rule(os.path.join("does", "not", "exist"), base="")
        self.assertEqual(rule.patterns, [])


class GlobSetTests(unittest.TestCase):
    def test_empty_set_is_falsy(self):
        self.assertFalse(GlobSet())

    def test_include_globs_match_basenames_and_paths(self):
        globs = GlobSet(["*.py", "docs/**"])
        self.assertTrue(globs.matches("src/app.py"))
        self.assertTrue(globs.matches("docs/a/b.md"))
        self.assertFalse(globs.matches("README.md"))

    def test_negated_glob_excludes(self):
        globs = GlobSet(["*.py", "!tests/*.py"])
        self.assertTrue(globs.matches("src/app.py"))
        self.assertFalse(globs.matches("tests/test_app.py"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
