"""Tests for token estimation and file-type knowledge."""

from __future__ import annotations

import unittest

from ctxpack.languages import (
    any_secret,
    is_binary_extension,
    is_secret_name,
    language_for,
)
from ctxpack.tokens import DEFAULT_RATIO, estimate_tokens, format_tokens


class EstimateTests(unittest.TestCase):
    def test_empty_text_costs_nothing(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_ascii_uses_the_ratio(self):
        text = "a" * 400
        self.assertEqual(estimate_tokens(text), 100)
        self.assertEqual(estimate_tokens(text, ratio=8.0), 50)

    def test_non_ascii_costs_one_token_per_character(self):
        self.assertEqual(estimate_tokens("中文测试"), 4)

    def test_mixed_text_adds_both_buckets(self):
        self.assertEqual(estimate_tokens("abcd中文"), 1 + 2)

    def test_monotonic_in_length(self):
        self.assertLess(estimate_tokens("hello"), estimate_tokens("hello world, friend"))

    def test_default_ratio_is_the_documented_value(self):
        self.assertEqual(DEFAULT_RATIO, 4.0)

    def test_invalid_ratio_rejected(self):
        with self.assertRaises(ValueError):
            estimate_tokens("text", ratio=0)


class FormatTests(unittest.TestCase):
    def test_thousands_separator(self):
        self.assertEqual(format_tokens(1234567), "1,234,567")
        self.assertEqual(format_tokens(0), "0")


class LanguageTests(unittest.TestCase):
    def test_extension_lookup(self):
        self.assertEqual(language_for("cli.py"), "python")
        self.assertEqual(language_for("App.TSX"), "tsx")
        self.assertEqual(language_for("data.csv"), "csv")

    def test_filename_lookup_beats_extension_lookup(self):
        self.assertEqual(language_for("Dockerfile"), "dockerfile")
        self.assertEqual(language_for("Makefile"), "makefile")
        self.assertEqual(language_for(".gitignore"), "gitignore")

    def test_unknown_returns_none(self):
        self.assertIsNone(language_for("mystery.qqq"))


class BinaryTests(unittest.TestCase):
    def test_media_and_archives_are_binary(self):
        for name in ("logo.png", "song.mp3", "archive.tar.gz", "app.exe", "report.pdf"):
            self.assertTrue(is_binary_extension(name), name)

    def test_source_files_are_not_binary(self):
        for name in ("main.py", "README.md", "config.toml", "logo.svg"):
            self.assertFalse(is_binary_extension(name), name)


class SecretTests(unittest.TestCase):
    def test_obvious_secrets_are_detected(self):
        for name in (".env", ".env.production", "server.pem", "id_rsa", ".netrc", "keystore.jks"):
            self.assertTrue(is_secret_name(name), name)

    def test_templates_and_public_keys_are_allowed(self):
        for name in (".env.example", ".env.sample", "id_rsa.pub", "notes.md"):
            self.assertFalse(is_secret_name(name), name)

    def test_any_secret_helper(self):
        self.assertTrue(any_secret(["a.py", ".env"]))
        self.assertFalse(any_secret(["a.py", "b.py"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
