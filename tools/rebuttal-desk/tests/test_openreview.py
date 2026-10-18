import tempfile
import unittest
from pathlib import Path

import yaml

from rebuttal_desk.openreview import import_openreview
from rebuttal_desk.workspace import WorkspaceError, load_workspace


def note(
    note_id,
    kind,
    author,
    content,
    children="",
    date="01 Jan 2025, 10:00",
    title="Original title",
    replying_to=None,
):
    parent = (
        f'<div class="parent-title"><h5>Replying to {replying_to}</h5></div>'
        if replying_to
        else ""
    )
    return f'''<div class="note" data-id="{note_id}">
    {parent}<div class="heading"><h4>{title}</h4></div>
    <div class="subheading"><span class="invitation">{kind}</span>
    <span class="signatures">by {author}</span><span class="created-date">{date}</span></div>
    <div class="note-content-container"><div class="note-content">{content}</div></div>
    <div class="note-replies">{children}</div></div>'''


def field(heading, body):
    return f"""<div><strong class="note-content-field">{heading}</strong>
    <div class="note-content-value">{body}</div></div>"""


class OpenReviewImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "workspace"
        self.html = self.root / "capture.html"

    def capture(self, notes):
        self.html.write_text(
            '<div id="content"><h2>Original paper title</h2></div>'
            '<div id="forum-replies">' + notes + "</div>"
        )

    def test_import_yaml_content_identity_and_threads(self):
        reply = note(
            "reply1", "Official Comment", "Authors", field("Comment:", "A reply")
        )
        math = '<span class="katex"><span>visual math</span><annotation encoding="application/x-tex">x_1^2</annotation></span>'
        content = field(
            "Claims And Evidence:", "<p>Exact wording &amp; punctuation.</p>"
        )
        content += field(
            "Requested Changes:", "<ul><li>First</li><li>Second</li></ul>" + math
        )
        self.capture(
            note("note1", "Review", "Reviewer aB12", content, reply)
            + note(
                "note2",
                "Decision",
                "Action Editor ed34 (Personal Name)",
                field("Decision:", "Accept"),
            )
        )
        self.assertEqual(import_openreview(self.html, self.output), (3, 2))
        self.assertFalse(list(self.output.rglob("*.json")))
        raw = yaml.safe_load((self.output / "reviews/note1.yaml").read_text())
        self.assertEqual(raw["sections"][0]["heading"], "Claims And Evidence:")
        self.assertEqual(raw["sections"][0]["content"], "Exact wording & punctuation.")
        workspace = load_workspace(self.output)
        review = workspace["reviews"][0]
        self.assertEqual(review["id"], "aB12")
        self.assertEqual(review["concerns"], [])
        self.assertEqual(review["comments"][0]["id"], "reply1")
        self.assertIn("<li>First</li>", review["document"]["html"])
        self.assertIn("x_1^2", review["document"]["html"])
        self.assertEqual(workspace["reviews"][1]["label"], "Action Editor ed34")
        with self.assertRaises(WorkspaceError):
            import_openreview(self.html, self.output)

    def test_conversation_chronology_types_and_explicit_reply_links(self):
        later = note(
            "later",
            "Official Comment",
            "Reviewer Ab12",
            field("Comment:", "Follow-up"),
            date="03 Jan 2025, 10:00",
            title="Later comment",
            replying_to="Earlier response",
        )
        earlier = note(
            "earlier",
            "Official Comment",
            "Authors",
            field("Comment:", "Answer"),
            date="02 Jan 2025, 10:00",
            title="Earlier response",
        )
        self.capture(
            note(
                "review",
                "Review",
                "Reviewer Ab12",
                field("Review:", "Question"),
                later + earlier,
            )
        )
        import_openreview(self.html, self.output)
        review = yaml.safe_load((self.output / "reviews/review.yaml").read_text())
        conversation = review["conversation"]
        self.assertEqual([c["id"] for c in conversation], ["earlier", "later"])
        self.assertEqual(
            [c["type"] for c in conversation], ["author_response", "reviewer_comment"]
        )
        self.assertEqual(conversation[1]["reply_to"], "earlier")
        self.assertEqual(conversation[0]["created_at"], "2025-01-02T10:00")
        loaded = load_workspace(self.output)["reviews"][0]["comments"]
        self.assertEqual([c["id"] for c in loaded], ["earlier", "later"])

    def test_original_checksum_and_separate_annotation_content(self):
        self.capture(
            note(
                "review",
                "Review",
                "Reviewer Ab12",
                field("Question:", "Original wording"),
            )
        )
        import_openreview(self.html, self.output)
        path = self.output / "reviews/review.yaml"
        raw = yaml.safe_load(path.read_text())
        section = raw["sections"][0]
        self.assertEqual(section["annotated_content"], section["content"])
        section["annotated_content"] = (
            '<concern id="C1" type="question">Original wording</concern>'
        )
        path.write_text(yaml.safe_dump(raw))
        load_workspace(self.output)
        for key, value in [
            ("heading", "Changed heading"),
            ("content", "Changed wording"),
        ]:
            with self.subTest(key=key):
                changed = yaml.safe_load(path.read_text())
                changed["sections"][0][key] = value
                path.write_text(yaml.safe_dump(changed))
                with self.assertRaisesRegex(WorkspaceError, "checksum mismatch"):
                    load_workspace(self.output)
                path.write_text(yaml.safe_dump(raw))
        del raw["content_checksum"]
        path.write_text(yaml.safe_dump(raw))
        with self.assertRaisesRegex(WorkspaceError, "checksum mismatch"):
            load_workspace(self.output)

    def test_unloaded_malformed_and_unsafe_input(self):
        for content in [
            "<h2>Title</h2>",
            note("../escape", "Review", "Reviewer abc", field("Text:", "Hi")),
            '<div class="note" data-id="abc"></div>',
        ]:
            with self.subTest(content=content):
                self.capture(content)
                with self.assertRaises(WorkspaceError):
                    import_openreview(self.html, self.output)
                self.assertFalse(self.output.exists())
