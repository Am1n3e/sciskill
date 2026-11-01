"""Regressions for selecting spelling from TeXtidote's pinned report format."""

from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sciskill.latex.spelling import spelling_findings, textidote_jar

# Real TeXtidote 0.9 output: a wrapped spelling message and grammar advice.
REPORT = r"""main.tex

* L3C26-L3C32 Possible spelling mistake found. Suggestions: [spelling,
  spewing, spieling] (25) [lt:en:MORFOLOGIK_RULE_EN_US]
  This sentence contains a speling mistake.
                           ^^^^^^^
* L5C8-L5C14 This sentence does not start with an uppercase letter.
  Suggestions: [Section] (81) [lt:en:UPPERCASE_SENTENCE_START]
  \input{section}
         ^^^^^^^
section.tex

* L1C33-L1C42 Possible spelling mistake found. Suggestions: [misspelling] (32)
  [lt:en:MORFOLOGIK_RULE_EN_US]
  The included section contains a misspeling.
                                  ^^^^^^^^^^
"""


def summary(count):
    return f"Found {count} warning(s)\nTotal analysis time: 6 second(s)\n"


class SpellingReportTests(unittest.TestCase):
    def test_selects_spelling_with_source_locations_across_files(self):
        findings = spelling_findings(REPORT, summary(3), 3)
        self.assertEqual(len(findings), 2)
        self.assertTrue(findings[0].startswith("main.tex:3:26:"))
        self.assertTrue(findings[1].startswith("section.tex:1:33:"))
        self.assertIn("misspelling", findings[1])

    def test_grammar_does_not_fail_spelling(self):
        grammar = REPORT[REPORT.index("* L5") : REPORT.index("section.tex\n")]
        self.assertEqual(spelling_findings(grammar, summary(1), 1), [])

    def test_single_file_keeps_its_actual_filename(self):
        report = REPORT[REPORT.index("* L3") : REPORT.index("* L5")]
        findings = spelling_findings(report, summary(1), 1, "content/intro.tex")
        self.assertTrue(findings[0].startswith("content/intro.tex:3:26:"))

    def test_corrupt_cached_jar_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / "textidote-0.9.jar").write_bytes(b"not the official release")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                textidote_jar(cache)

    def test_clean_report_passes(self):
        self.assertEqual(spelling_findings("Everything is OK!\n", summary(0), 0), [])

    def test_execution_errors_cannot_look_clean(self):
        for stderr, code in [
            ("Unable to access jarfile", 1),
            (summary(0) + "File missing.tex not found (skipping)", 0),
            (summary(0) + "java.io.IOException: failed", 0),
            (summary(0), 125),
        ]:
            with self.subTest(stderr=stderr, code=code):
                with self.assertRaises(ValueError):
                    spelling_findings("", stderr, code)

    def test_unrecognized_or_truncated_reports_fail(self):
        with self.assertRaises(ValueError):
            spelling_findings("", summary(0), 0)
        with self.assertRaises(ValueError):
            spelling_findings(REPORT, summary(4), 4)
        with self.assertRaises(ValueError):
            spelling_findings("* L1C1-L1C3 Unknown report format\n", summary(1), 1)


if __name__ == "__main__":
    unittest.main()
