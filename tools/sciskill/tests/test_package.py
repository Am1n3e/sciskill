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
            self.assertIn("bib_lint/pdf_input/worker.py", names)
            self.assertIn("bib_lint/pdf_evidence.py", names)
            self.assertIn("bib_lint/verification/queues.py", names)
            metadata = wheel.read(next(name for name in names if name.endswith('/METADATA'))).decode()
            self.assertIn("Requires-Dist: huey", metadata)
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

    def test_pdf_preview_runs_from_installed_shared_entrypoint(self):
        source = self.directory / "research paper.PDF"
        write_research_pdf(source)
        original = source.read_bytes()

        def preview(base_url):
            import http.cookiejar

            browser = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
            )
            with browser.open(base_url + "/api/state") as response:
                state = json.loads(response.read())
            request = urllib.request.Request(
                base_url + "/api/action",
                data=json.dumps(
                    {
                        "action": "parse",
                        "bibliography": str(source),
                        "output": str(self.directory / "pdf-audit"),
                    }
                ).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-CSRF-Token": state["csrf"],
                },
            )
            with browser.open(request, timeout=30) as response:
                state = json.loads(response.read())
            self.assertIsNone(state["error"])
            self.assertEqual(state["metadata"]["input_kind"], "pdf")
            self.assertEqual(state["summary"]["completed"], 0)
            self.assertEqual(state["summary"]["extraction"]["occurrence_count"], 1)
            with browser.open(base_url + "/api/reference?key=pdf-ref-0001") as response:
                detail = json.loads(response.read())
            self.assertEqual(detail["pdf"]["fragments"][0]["page"], 1)
            self.assertEqual(detail["entry"]["fields"]["title"], "An Example Paper")
            self.assertFalse((self.directory / "pdf-audit/cache").exists())

        self.check_viewer("bib-lint", "", after_ready=preview)
        self.assertEqual(source.read_bytes(), original)
        invalid = self.directory / "invalid.pdf"
        invalid.write_bytes(b"not a PDF")
        result = subprocess.run(
            [*self.command, "bib-lint", "verify", str(invalid), "--json"],
            cwd=self.directory,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["extraction"]["state"], "failed")
        self.assertTrue(envelope["error"]["diagnostics"])
        self.assertFalse((self.directory / "invalid.bib-lint").exists())

    def check_viewer(self, tool, path, after_ready=None):
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
                        self.assertIn("SciSkill" if tool == "bib-lint" else "Science Skills", page.read().decode())
                    if after_ready:
                        after_ready(f"http://127.0.0.1:{port}")
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


def write_research_pdf(path):
    """Write a tiny real text PDF using only stdlib in the installed-package gate."""
    content = (
        b"BT /F1 12 Tf 50 700 Td (References) Tj 0 -20 Td "
        b"([1] Jane Smith. An Example Paper. Example Journal, 2025.) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
    ]
    raw = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    xref = len(raw)
    raw.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    raw.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets))
    raw.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(raw)
