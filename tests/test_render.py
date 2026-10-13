"""Tests for the Markdown renderer."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ctxpack.render import build_tree, code_fence, render_document, render_tree
from ctxpack.walk import PackedFile, Skipped


def packed(path: str, text: str = "x = 1\n", language="python", size=None) -> PackedFile:
    return PackedFile(
        root="/repo",
        path=path,
        size=len(text.encode("utf-8")) if size is None else size,
        text=text,
        lines=len(text.splitlines()),
        language=language,
        tokens=10,
        priority=0 if path.startswith("README") else 1,
    )


class CodeFenceTests(unittest.TestCase):
    def test_default_fence_is_three_backticks(self):
        self.assertEqual(code_fence("print(1)"), "```")

    def test_fence_grows_past_embedded_runs(self):
        self.assertEqual(code_fence("text with ``` inside"), "````")
        self.assertEqual(code_fence("text with ```` inside"), "`````")

    def test_generated_fence_actually_contains_the_text(self):
        text = 'a = """```"""\n'
        fence = code_fence(text)
        block = f"{fence}python\n{text}{fence}"
        self.assertEqual(block.count(fence), 2)


class TreeTests(unittest.TestCase):
    def test_tree_orders_directories_before_files(self):
        tree = build_tree(["src/app.py", "README.md", "src/deep/mod.py"])
        self.assertEqual(
            render_tree(tree),
            [
                "├── src/",
                "│   ├── deep/",
                "│   │   └── mod.py",
                "│   └── app.py",
                "└── README.md",
            ],
        )

    def test_ascii_style_uses_ascii_only(self):
        tree = build_tree(["a.txt"])
        self.assertEqual(render_tree(tree, style="ascii"), ["`-- a.txt"])

    def test_single_file_tree(self):
        self.assertEqual(render_tree(build_tree(["solo.py"])), ["└── solo.py"])


class DocumentTests(unittest.TestCase):
    def render(self, **kwargs):
        sections = kwargs.pop(
            "sections", [("repo", [packed("README.md", "# hi\n", language="markdown")])]
        )
        return render_document(
            sections=sections,
            version="0.1.0",
            generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            **kwargs,
        )

    def test_header_contains_version_timestamp_and_root(self):
        document = self.render()
        self.assertIn("# ctxpack", document)
        self.assertIn("v0.1.0", document)
        self.assertIn("2026-01-02 03:04 UTC", document)
        self.assertIn("`repo`", document)

    def test_sections_are_present(self):
        document = self.render()
        self.assertIn("## Overview", document)
        self.assertIn("## Directory tree", document)
        self.assertIn("## Files", document)
        self.assertIn("### `README.md`", document)
        self.assertIn("```markdown", document)

    def test_tree_can_be_disabled(self):
        self.assertNotIn("## Directory tree", self.render(show_tree=False))

    def test_multiple_roots_are_labeled(self):
        document = self.render(
            sections=[("core", [packed("a.py")]), ("docs", [packed("b.md", language="markdown")])]
        )
        self.assertIn("### Root `core`", document)
        self.assertIn("### `core/a.py`", document)
        self.assertIn("### `docs/b.md`", document)

    def test_deferred_files_are_listed(self):
        document = self.render(omitted=[packed("huge.py", size=999)], max_tokens=1000)
        self.assertIn("## Deferred by token budget", document)
        self.assertIn("`huge.py`", document)
        self.assertIn("Token budget: 1,000", document)
        # CommonMark needs a blank line before a list that follows a paragraph.
        self.assertIn("include them.\n\n- `huge.py`", document)

    def test_secret_skips_are_surfaced(self):
        document = self.render(
            skipped=[Skipped(".env", "looks like a secret (pass --include-secrets)")]
        )
        self.assertIn("## Skipped as secret-like", document)
        self.assertIn("override.\n\n- `.env`", document)

    def test_no_files_case_is_explicit(self):
        document = self.render(sections=[("repo", [])])
        self.assertIn("## No files matched", document)

    def test_output_ends_with_exactly_one_newline(self):
        document = self.render()
        self.assertTrue(document.endswith("\n"))
        self.assertFalse(document.endswith("\n\n"))

    def test_blank_line_separates_header_from_first_heading(self):
        document = self.render()
        self.assertNotIn("tokens (estimated)\n## Overview", document)
        self.assertIn("tokens (estimated)\n\n## Overview", document)

    def test_sections_are_separated_by_exactly_one_blank_line(self):
        document = self.render()
        self.assertIn("## Overview\n\n| Language | Files | Lines |", document)
        self.assertIn("## Directory tree\n\n```text", document)
        self.assertIn("```\n\n## Files", document)
        self.assertNotIn("\n\n\n", document)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
