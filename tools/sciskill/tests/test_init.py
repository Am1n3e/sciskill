"""Project initialization preserves user files and requires gitignore opt-in."""

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sciskill.project import initialize


class InitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "paper.tex").write_text("Original manuscript")
        (self.root / "references.bib").write_text("Original bibliography")

    def test_inputs_and_no_gitignore_by_default(self):
        config_path = initialize(
            self.root, latex="paper.tex", bib="references.bib", venue="NeurIPS"
        )
        self.assertEqual(
            yaml.safe_load(config_path.read_text()),
            {
                "version": 1,
                "latex": "paper.tex",
                "bib": "references.bib",
                "venue": "NeurIPS",
            },
        )
        self.assertTrue((self.root / ".sciskill/cache").is_dir())
        self.assertTrue((self.root / ".sciskill/tmp").is_dir())
        self.assertFalse((self.root / ".gitignore").exists())
        self.assertEqual((self.root / "paper.tex").read_text(), "Original manuscript")
        self.assertEqual(
            (self.root / "references.bib").read_text(), "Original bibliography"
        )

    def test_opt_out_leaves_existing_gitignore_unchanged(self):
        path = self.root / ".gitignore"
        content = b"# Preserve formatting\r\n*.aux"
        path.write_bytes(content)
        initialize(self.root)
        self.assertEqual(path.read_bytes(), content)

    def test_gitignore_opt_in_is_idempotent(self):
        path = self.root / ".gitignore"
        path.write_text("*.aux")
        initialize(self.root, update_gitignore=True)
        initialize(self.root, update_gitignore=True)
        self.assertEqual(path.read_text(), "*.aux\n.sciskill/\n")
        path.write_text("/.sciskill/\n")
        initialize(self.root, update_gitignore=True)
        self.assertEqual(path.read_text(), "/.sciskill/\n")

    def test_rerun_preserves_configuration_and_artifacts(self):
        path = initialize(
            self.root, latex="paper.tex", bib="references.bib", venue="ICLR"
        )
        artifact = self.root / ".sciskill/cache/evidence.txt"
        artifact.write_text("keep")
        initialize(self.root)
        self.assertEqual(yaml.safe_load(path.read_text())["venue"], "ICLR")
        initialize(self.root, venue="NeurIPS")
        self.assertEqual(yaml.safe_load(path.read_text())["latex"], "paper.tex")
        self.assertEqual(yaml.safe_load(path.read_text())["venue"], "NeurIPS")
        self.assertEqual(artifact.read_text(), "keep")

    def test_invalid_input_does_not_create_project_state(self):
        with self.assertRaises(ValueError):
            initialize(self.root, bib="missing.bib", update_gitignore=True)
        self.assertFalse((self.root / ".sciskill").exists())
        self.assertFalse((self.root / ".gitignore").exists())

    def test_invalid_existing_configuration_is_preserved(self):
        path = initialize(self.root)
        path.write_text("version: 99\n")
        with self.assertRaises(ValueError):
            initialize(self.root)
        self.assertEqual(path.read_text(), "version: 99\n")

    def test_symlinked_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as target:
            (self.root / ".sciskill").symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                initialize(self.root)
            self.assertEqual(list(Path(target).iterdir()), [])
