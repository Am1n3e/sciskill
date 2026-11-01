"""Project boundaries and output safety for the installed LaTeX commands."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sciskill.latex.runner import Project, clean


class LatexProjectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        (self.root / "main.tex").write_text("manuscript")

    def test_default_and_manifest_source(self):
        self.assertEqual(Project.load(self.root).main, Path("main.tex"))
        (self.root / ".sciskill").mkdir()
        (self.root / "paper.tex").write_text("paper")
        (self.root / ".sciskill/config.yaml").write_text(
            "version: 1\nlatex: paper.tex\n"
        )
        self.assertEqual(Project.load(self.root).main, Path("paper.tex"))
        self.assertEqual(Project.load(self.root, "main.tex").main, Path("main.tex"))

    def test_manifest_directory_and_nested_main(self):
        (self.root / "paper").mkdir()
        (self.root / "paper/main.tex").write_text("paper")
        (self.root / ".sciskill").mkdir()
        (self.root / ".sciskill/config.yaml").write_text("version: 1\nlatex: paper\n")
        project = Project.load(self.root)
        self.assertEqual(project.root, self.root / "paper")
        self.assertEqual(project.main, Path("main.tex"))

    def test_external_source_is_rejected(self):
        (self.root / "escape.tex").symlink_to(Path(__file__))
        with self.assertRaisesRegex(ValueError, "inside"):
            Project.load(self.root, "escape.tex")

    def test_directory_source_cannot_follow_an_external_main_symlink(self):
        (self.root / "paper").mkdir()
        (self.root / "paper/main.tex").symlink_to(Path(__file__))
        with self.assertRaisesRegex(ValueError, "inside"):
            Project.load(self.root, "paper")

    def test_clean_removes_only_output_without_requiring_a_manuscript(self):
        (self.root / "main.tex").unlink()
        output = self.root / ".out"
        output.mkdir()
        (output / "main.pdf").write_bytes(b"generated")
        clean(self.root)
        clean(self.root)
        self.assertFalse(output.exists())

    def test_symlinked_output_is_neither_built_through_nor_cleaned(self):
        outside = self.root / "assets"
        outside.mkdir()
        (outside / "keep").write_text("source")
        (self.root / ".out").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            Project.load(self.root).prepare_output()
        with self.assertRaisesRegex(ValueError, "symlink"):
            clean(self.root)
        self.assertEqual((outside / "keep").read_text(), "source")


if __name__ == "__main__":
    unittest.main()
