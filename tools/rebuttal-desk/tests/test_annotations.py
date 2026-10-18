import unittest

from rebuttal_desk.annotations import annotation_markup


class AnnotationTests(unittest.TestCase):
    def test_exact_text_and_safe_type_metadata(self):
        source = "Before **the concern** after."
        annotated = 'Before <science-skills-annotation id="R-C1" type="response">**the concern**</science-skills-annotation> after.'
        marked, entries = annotation_markup(source, annotated)
        self.assertIn('data-annotation-type="response"', marked)
        self.assertEqual(
            entries, [{"id": "R-C1", "type": "response", "source": "**the concern**"}]
        )

    def test_reject_changed_text_invalid_metadata_and_unbalanced_tags(self):
        for marked in [
            '<science-skills-annotation id="C1" type="question">text</science-skills-annotation>',
            '<science-skills-annotation id="C1" type="response" onclick="bad()">text</science-skills-annotation>',
            '<science-skills-annotation id="C1" type="response">text',
            "text</science-skills-annotation>",
            '<science-skills-annotation id="C1" type="response">changed</science-skills-annotation>',
        ]:
            with self.subTest(marked=marked), self.assertRaises(ValueError):
                annotation_markup("text", marked)
