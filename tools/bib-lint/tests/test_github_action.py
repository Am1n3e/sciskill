"""The PR summary preserves uncertain outcomes and escapes citation keys."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("bib_action", ROOT / "actions/bib-lint/check.py")
action = importlib.util.module_from_spec(spec)
spec.loader.exec_module(action)


class BibliographyActionTests(unittest.TestCase):
    def test_summary_no_new_entries(self):
        rendered = action.render({"summary": {"eligible": 0}, "complete": True}, {"items": []})
        self.assertIn("No new references", rendered)
        self.assertNotIn("Invalid", rendered)

    def test_summary_preserves_invalid_and_unknown(self):
        report = {
            "items": [
                {
                    "entry": {"key": "<script>|bad"},
                    "validations": {"correctness": {"complete": True, "is_correct": False}},
                },
                {
                    "entry": {"key": "uncertain"},
                    "validations": {
                        "correctness": {"complete": True, "is_correct": None, "methods": []}
                    },
                },
            ]
        }
        rendered = action.render({"summary": {"eligible": 2}, "complete": True}, report)
        self.assertIn("&lt;script&gt;|bad", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("Invalid", rendered)
        self.assertIn("Unresolved", rendered)

    def test_failed_audit_is_not_summarized_as_zero_new_entries(self):
        rendered = action.render(
            {"summary": None, "complete": False, "error": {"message": "Git <failed>"}}, None
        )
        self.assertIn("could not complete", rendered)
        self.assertIn("Git &lt;failed&gt;", rendered)
        self.assertNotIn("No new references", rendered)
