"""Tests for the git integration behind ``--diff``.

These build real repositories in temporary directories and shell out to git, so
they are skipped on machines without git on PATH.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from packdiff.git import GitError, changed_paths, is_inside, paths_within, repo_root
from support import GIT, git_commit, git_run, init_repo, make_tree


@unittest.skipUnless(GIT, "git is not installed")
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # realpath: on macOS the temporary directory is a symlink, and git
        # reports the resolved path.
        self.root = os.path.realpath(self._tmp.name)
        make_tree(
            self.root,
            {
                "README.md": "# demo\n",
                "src/app.py": "print('one')\n",
                "src/util.py": "VALUE = 1\n",
            },
        )
        init_repo(self.root)

    def changed(self, revision: str = "HEAD") -> set[str]:
        _, paths = changed_paths(revision, cwd=self.root)
        return paths

    def test_repo_root_is_resolved(self):
        # samefile rather than string equality: Windows may spell the same
        # directory with a different case or an 8.3 short name.
        self.assertTrue(os.path.samefile(repo_root(self.root), self.root))

    def test_clean_working_tree_reports_nothing(self):
        self.assertEqual(self.changed(), set())

    def test_uncommitted_edits_are_reported(self):
        make_tree(self.root, {"src/app.py": "print('two')\n"})
        self.assertEqual(self.changed(), {"src/app.py"})

    def test_untracked_files_count_as_changes(self):
        make_tree(self.root, {"src/new.py": "FRESH = True\n"})
        self.assertEqual(self.changed(), {"src/new.py"})

    def test_deleted_files_are_reported(self):
        os.remove(os.path.join(self.root, "src", "util.py"))
        self.assertEqual(self.changed(), {"src/util.py"})

    def test_staged_but_uncommitted_changes_are_reported(self):
        make_tree(self.root, {"src/app.py": "print('three')\n"})
        git_run(self.root, "add", "src/app.py")
        self.assertEqual(self.changed(), {"src/app.py"})

    def test_a_revision_packs_what_that_commit_introduced(self):
        make_tree(self.root, {"src/util.py": "VALUE = 2\n"})
        git_run(self.root, "add", "-A")
        git_commit(self.root, "bump value")
        self.assertEqual(self.changed("HEAD~1"), {"src/util.py"})

    def test_gitignored_files_are_not_treated_as_untracked(self):
        make_tree(self.root, {".gitignore": "*.log\n", "debug.log": "noise\n"})
        git_run(self.root, "add", ".gitignore")
        git_commit(self.root, "ignore logs")
        self.assertEqual(self.changed(), set())

    def test_unborn_head_treats_everything_as_new(self):
        with tempfile.TemporaryDirectory() as other:
            fresh = os.path.realpath(other)
            make_tree(fresh, {"a.txt": "a\n", "b/c.txt": "c\n"})
            git_run(fresh, "init", "-q")
            _, paths = changed_paths("HEAD", cwd=fresh)
            self.assertEqual(paths, {"a.txt", "b/c.txt"})

    def test_bad_revision_is_an_error(self):
        with self.assertRaises(GitError):
            changed_paths("no-such-revision", cwd=self.root)

    def test_directory_outside_a_repository_is_an_error(self):
        with tempfile.TemporaryDirectory() as other, self.assertRaises(GitError):
            changed_paths("HEAD", cwd=os.path.realpath(other))

    def test_missing_git_binary_is_reported_clearly(self):
        patch = mock.patch("subprocess.run", side_effect=FileNotFoundError())
        with patch, self.assertRaises(GitError) as caught:
            changed_paths("HEAD", cwd=self.root)
        self.assertIn("not found on PATH", str(caught.exception))

    def test_error_message_is_stripped_of_git_noise(self):
        with self.assertRaises(GitError) as caught:
            changed_paths("no-such-revision", cwd=self.root)
        message = str(caught.exception)
        self.assertNotIn("fatal:", message)
        self.assertNotIn("usage:", message)


class PathMappingTests(unittest.TestCase):
    """Path arithmetic, with no repository involved.

    The ``/repo`` paths below do not exist on any filesystem, on purpose: they
    pin the behaviour for a caller-supplied path that has *not* been resolved,
    which is where this code first broke on Windows (``realpath("/repo")`` is
    ``"/repo"`` on POSIX and ``D:\\repo`` there).
    """

    def test_root_inside_repository(self):
        self.assertTrue(is_inside("/repo/src", "/repo"))
        self.assertTrue(is_inside("/repo", "/repo"))

    def test_root_outside_repository(self):
        self.assertFalse(is_inside("/other", "/repo"))
        self.assertFalse(is_inside("/repository", "/repo"))

    def test_paths_are_rebased_onto_the_root(self):
        changed = {"src/a.py", "src/deep/b.py", "docs/c.md"}
        self.assertEqual(paths_within("/repo/src", "/repo", changed), {"a.py", "deep/b.py"})

    def test_paths_at_the_repository_root_are_unchanged(self):
        changed = {"src/a.py"}
        self.assertEqual(paths_within("/repo", "/repo", changed), changed)

    def test_unrelated_paths_are_dropped(self):
        self.assertEqual(paths_within("/repo/docs", "/repo", {"src/a.py"}), set())

    def test_a_single_file_root_contributes_its_own_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            # new.py is untracked but present on disk, which is the --diff case
            # for a file you have just created.
            make_tree(
                root,
                {"sub/one.py": "x = 1\n", "sub/two.py": "y = 2\n", "sub/new.py": "z = 3\n"},
            )
            one = os.path.join(root, "sub", "one.py")
            newline = os.path.join(root, "sub", "new.py")
            self.assertEqual(paths_within(one, root, {"sub/one.py"}), {"one.py"})
            self.assertEqual(paths_within(one, root, {"sub/two.py"}), set())
            self.assertEqual(paths_within(newline, root, {"sub/new.py"}), {"new.py"})

    def test_paths_within_handles_a_path_that_is_not_resolved(self):
        """A root spelled differently from its realpath must still work.

        Reached through a symlink so the mismatch is reproducible on Linux and
        macOS — on Windows the same thing happens constantly, because
        ``realpath("/repo")`` returns ``D:\\repo``.
        """
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.realpath(tmp)
            os.makedirs(os.path.join(real, "sub"), exist_ok=True)
            link = os.path.join(real, "link")
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:  # pragma: no cover
                self.skipTest(f"symlinks unavailable: {exc}")

            self.assertNotEqual(link, os.path.realpath(link))
            self.assertTrue(is_inside(os.path.join(link, "sub"), link))
            self.assertEqual(paths_within(real, link, {"src/a.py"}), {"src/a.py"})
            self.assertEqual(paths_within(os.path.join(link, "sub"), real, {"sub/b.py"}), {"b.py"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
