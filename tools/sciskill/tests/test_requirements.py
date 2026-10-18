"""Prerequisite failures stop initialization before any project writes."""

import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sciskill.project import main
from sciskill.requirements import check_required_tools


class RequiredToolsTests(unittest.TestCase):
    def test_missing_tools_are_reported_together(self):
        with (
            patch("sciskill.requirements.shutil.which", return_value=None),
            self.assertRaisesRegex(ValueError, "uv: not found.*uvx: not found"),
        ):
            check_required_tools()

    def test_broken_executable_is_not_ready(self):
        with (
            patch("sciskill.requirements.shutil.which", return_value="/tool"),
            patch(
                "sciskill.requirements.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, "", "failed"),
            ),
            self.assertRaisesRegex(ValueError, "version check failed"),
        ):
            check_required_tools()

    def test_timeout_is_not_ready(self):
        with (
            patch("sciskill.requirements.shutil.which", return_value="/tool"),
            patch(
                "sciskill.requirements.subprocess.run",
                side_effect=subprocess.TimeoutExpired("/tool", 10),
            ),
            self.assertRaisesRegex(ValueError, "could not run version check"),
        ):
            check_required_tools()

    def test_failed_preflight_preserves_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ignore = root / ".gitignore"
            ignore.write_bytes(b"*.aux\r\n")
            with (
                patch("sciskill.project.Path.cwd", return_value=root),
                patch(
                    "sciskill.requirements.shutil.which",
                    return_value=None,
                ),
                redirect_stderr(StringIO()),
                self.assertRaises(SystemExit) as result,
            ):
                main(["--update-gitignore"])
            self.assertEqual(result.exception.code, 2)
            self.assertFalse((root / ".sciskill").exists())
            self.assertEqual(ignore.read_bytes(), b"*.aux\r\n")
