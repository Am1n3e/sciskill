"""Deterministic records and provider doubles shared by tests."""

from bib_lint.verification.matching import input_record

ENTRY = {
    "key": "Example",
    "type": "article",
    "fields": {
        "title": "An Example Paper",
        "year": "2025",
        "journal": "Example Journal",
        "doi": "10.1234/example",
    },
    "persons": {
        "author": [
            {"first": ["Jane"], "middle": [], "prelast": [], "last": ["Smith"], "lineage": []}
        ]
    },
}
RECORD = input_record(ENTRY)
RECORD["url"] = "https://doi.org/10.1234/example"


class FakeClient:
    def __init__(self, data=None, text=None):
        self.data = data
        self.text = text
        self.evidence = []

    def json(self, *args, **kwargs):
        return self.data

    def get(self, *args, **kwargs):
        return self.text
