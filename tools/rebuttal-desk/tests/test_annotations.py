import unittest

from rebuttal_desk.annotations import annotation_markup


class AnnotationTests(unittest.TestCase):
    def test_exact_text_and_safe_type_metadata(self):
        source = "Before **the concern** after."
        annotated = 'Before <science-skills-annotation id="R-C1" type="clarification">**the concern**</science-skills-annotation> after.'
        marked, entries = annotation_markup(source, annotated)
        self.assertIn('data-annotation-type="clarification"', marked)
        self.assertEqual(
            entries,
            [{"id": "R-C1", "type": "clarification", "source": "**the concern**"}],
        )

    def test_optional_subtype_stays_on_the_annotation(self):
        marked, entries = annotation_markup(
            "text",
            '<science-skills-annotation id="C1" type="change_request" subtype="additional_experiments">text</science-skills-annotation>',
        )
        self.assertEqual(entries[0]["subtype"], "additional_experiments")
        self.assertIn('data-annotation-type="change_request"', marked)
        self.assertIn('data-annotation-subtype="additional_experiments"', marked)
        with self.assertRaises(ValueError):
            annotation_markup(
                "text",
                '<science-skills-annotation id="C1" type="change_request" subtype="">text</science-skills-annotation>',
            )

    def test_reject_changed_text_invalid_metadata_and_unbalanced_tags(self):
        for marked in [
            '<science-skills-annotation id="C1" type="question">text</science-skills-annotation>',
            '<science-skills-annotation id="C1" type="clarification" onclick="bad()">text</science-skills-annotation>',
            '<science-skills-annotation id="C1" type="clarification">text',
            "text</science-skills-annotation>",
            '<science-skills-annotation id="C1" type="clarification">changed</science-skills-annotation>',
        ]:
            with self.subTest(marked=marked), self.assertRaises(ValueError):
                annotation_markup("text", marked)
