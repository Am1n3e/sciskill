"""Installed-wheel acceptance tests; run explicitly on a Linux Docker runner."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PREAMBLE = "\\documentclass{article}\n\\begin{document}\n"


class LatexIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="sciskill-paper-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.command = ["uvx", "--from", os.environ["SCISKILL_TEST_WHEEL"], "sciskill"]

    def cli(self, task, *arguments, code=0):
        result = subprocess.run(
            [*self.command, f"latex-{task}", *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", *arguments], cwd=self.root, text=True
        ).strip()

    def commit(self):
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "-qm",
            "Paper",
        )
        return self.git("rev-parse", "HEAD")

    def test_default_build_lint_spell_and_clean(self):
        source = self.root / "main.tex"
        source.write_text(PREAMBLE + "This is a simple sentence.\n\\end{document}\n")
        self.cli("build")
        self.assertTrue((self.root / ".out/main.pdf").read_bytes().startswith(b"%PDF"))
        self.cli("lint")
        # Developers may reuse a verified local cache; CI exercises the download.
        cache = os.environ.get("SCISKILL_TEST_TEXTIDOTE_JAR")
        if cache:
            (self.root / ".out/tools").mkdir()
            shutil.copyfile(cache, self.root / ".out/tools/textidote-0.9.jar")
        self.cli("spell")
        source.write_text(
            PREAMBLE + "This sentence contains a speling mistake.\n\\end{document}\n"
        )
        self.assertIn("main.tex:", self.cli("spell", code=1))
        self.cli("clean")
        self.assertFalse((self.root / ".out").exists())
        self.assertIn("speling", source.read_text())

    def test_diff_of_included_prose_equation_and_bibliography(self):
        self.git("init", "-q")
        (self.root / ".gitignore").write_text(".out/\n")
        (self.root / "paper.tex").write_text(
            PREAMBLE + "\\input{intro}\n\\bibliographystyle{plain}\n"
            "\\bibliography{references}\n\\end{document}\n"
        )
        (self.root / "intro.tex").write_text(
            "We present a result~\\cite{example}. $x=1$.\n"
        )
        bibliography = self.root / "references.bib"
        bibliography.write_text(
            "@book{example,author={Jane Smith},title={Original title},year={2025},publisher={Example Press}}\n"
        )
        base = self.commit()
        (self.root / "intro.tex").write_text(
            "We introduce a result~\\cite{example}. $x=2$.\n"
        )
        bibliography.write_text(
            bibliography.read_text().replace("Original title", "Revised title")
        )
        head = self.commit()
        self.cli("diff", "--main", "paper.tex", "--base", base, "--head", head)
        for name in ("paper.pdf", "paper-diff.pdf"):
            self.assertTrue(
                (self.root / ".out" / name).read_bytes().startswith(b"%PDF")
            )
        # Read actual output; distinguish a rendered diff from a clean PDF copy.
        import pdfplumber

        with pdfplumber.open(self.root / ".out/paper-diff.pdf") as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        for word in ("present", "introduce", "Original", "Revised"):
            self.assertIn(word, text)
        # Papers without a bibliography are also valid diff inputs.
        (self.root / "paper.tex").write_text(
            PREAMBLE + "A short paper.\n\\end{document}\n"
        )
        without_bib = self.commit()
        self.cli(
            "diff", "--main", "paper.tex", "--base", without_bib, "--head", without_bib
        )


if __name__ == "__main__":
    unittest.main()
