"""Exercise the published artifact without relying on either tool checkout."""

import json
import os
import socket
import subprocess
import tempfile
import time
import tomllib
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        subprocess.run(
            ["uv", "build", "--out-dir", str(cls.directory / "dist")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.wheel = next((cls.directory / "dist").glob("*.whl"))
        cls.command = ["uvx", "--from", str(cls.wheel), "sciskill"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [*self.command, *map(str, arguments)],
            cwd=self.directory,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        ).stdout

    def test_version_help_and_assets(self):
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
            "version"
        ]
        self.assertEqual(self.run_cli("--version").strip(), f"sciskill {version}")
        self.assertIn("sciskill bib-lint", self.run_cli("bib-lint", "--help"))
        self.assertIn("sciskill rebuttal", self.run_cli("rebuttal", "--help"))
        with zipfile.ZipFile(self.wheel) as wheel:
            names = wheel.namelist()
            for package in ("bib_lint/viewer", "rebuttal_desk"):
                self.assertIn(f"{package}/static/index.html", names)
            self.assertFalse(
                any(".local/" in name or "references.json" in name for name in names)
            )

    def test_installed_init_command(self):
        import yaml

        paper = self.directory / "paper.tex"
        bib = self.directory / "references.bib"
        paper.write_text("Original manuscript")
        bib.write_text("Original bibliography")
        self.run_cli("init", "--latex", paper, "--bib", bib, "--venue", "ICLR")
        config = self.directory / ".sciskill/config.yaml"
        data = yaml.safe_load(config.read_text())
        self.assertEqual(data["latex"], "paper.tex")
        self.assertEqual(data["bib"], "references.bib")
        self.assertEqual(data["venue"], "ICLR")
        self.assertFalse((self.directory / ".gitignore").exists())
        self.run_cli("init", "--update-gitignore")
        self.run_cli("init", "--update-gitignore")
        self.assertEqual((self.directory / ".gitignore").read_text(), ".sciskill/\n")
        self.assertEqual(yaml.safe_load(config.read_text()), data)

    def test_workflows_and_both_viewers(self):
        bib = self.directory / "empty.bib"
        bib.write_text("% empty bibliography\n")
        result = json.loads(self.run_cli("bib-lint", "verify", bib, "--json"))
        self.assertTrue(result["complete"])
        workspace = self.directory / "rebuttal"
        self.run_cli("rebuttal", "init", workspace)
        self.assertIn(
            "Valid structure:", self.run_cli("rebuttal", "validate", workspace)
        )
        for tool, path in (("bib-lint", result["output_dir"]), ("rebuttal", workspace)):
            with self.subTest(tool=tool):
                self.check_viewer(tool, path)

    def check_viewer(self, tool, path):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [
                *self.command,
                tool,
                "view",
                str(path),
                "--no-browser",
                "--port",
                str(port),
            ],
            cwd=self.directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/", timeout=1
                    ) as page:
                        self.assertIn("Science Skills", page.read().decode())
                    return
                except (urllib.error.URLError, TimeoutError):
                    if process.poll() is not None:
                        self.fail(process.communicate()[1])
                    time.sleep(0.1)
            self.fail("Viewer did not start")
        finally:
            import signal

            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
            process.communicate(timeout=10)
