"""Exercise revision selection and snapshot extraction with real Git repositories."""

from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sciskill.latex.diff import comparison_revisions, export_revision


class PaperDiffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        (self.root / "main.tex").write_text("Original manuscript\n")
        self.original = self.commit("Initial manuscript")

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", *arguments], cwd=self.root, text=True
        ).strip()

    def commit(self, message):
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "-qm",
            message,
        )
        return self.git("rev-parse", "HEAD")

    def test_comparison_excludes_changes_only_on_target_branch(self):
        (self.root / "main.tex").write_text("PR manuscript\n")
        head = self.commit("Update manuscript")
        self.git("checkout", "-qb", "target", self.original)
        (self.root / "README.md").write_text("Unrelated target update\n")
        target = self.commit("Target update")
        self.assertEqual(
            comparison_revisions(self.root, target, head), (self.original, head)
        )

    def test_snapshot_contains_exact_revision_and_no_untracked_files(self):
        (self.root / "main.tex").write_text("Uncommitted manuscript\n")
        (self.root / "private.txt").write_text("Not tracked\n")
        destination = self.root / "snapshot"
        export_revision(self.root, self.original, destination)
        self.assertEqual(
            (destination / "main.tex").read_text(), "Original manuscript\n"
        )
        self.assertFalse((destination / "private.txt").exists())
        self.assertFalse((destination / ".git").exists())

    def test_symlinks_in_snapshots_are_rejected(self):
        (self.root / "escape").symlink_to("/tmp")
        revision = self.commit("Add symlink")
        with self.assertRaisesRegex(ValueError, "Unsupported archive entry"):
            export_revision(self.root, revision, self.root / "snapshot")

    def test_invalid_revision_is_not_treated_as_a_git_option(self):
        with self.assertRaises(subprocess.CalledProcessError):
            comparison_revisions(self.root, "--help", "HEAD")


if __name__ == "__main__":
    unittest.main()
