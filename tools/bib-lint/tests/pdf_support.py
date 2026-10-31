"""Hand-written PDF report examples independent of the extraction implementation."""

import copy


def pdf_report():
    text = "Jane Smith. Example Paper. Example Journal, 2025."
    report = {
        "schema_version": 4,
        "source": {"name": "paper.pdf", "sha256": "a" * 64},
        "summary": {"total_count": 1, "total_not_used": None},
        "verification_scope": {"mode": "all", "eligible_keys": ["pdf-ref-0001"]},
        "extraction": {
            "schema_version": 1,
            "document": {
                "name": "paper.pdf",
                "sha256": "a" * 64,
                "pages": 1,
                "page_sizes": [{"width": 612, "height": 792}],
            },
            "extractor": {"id": "pdfplumber", "version": "0.11.9"},
            "parser": {"id": "bib-lint-local", "version": "1"},
            "settings": {"max_pages": 200},
            "state": "complete",
            "reference_pages": [1],
            "unresolved_fragments": 0,
            "diagnostics": [],
        },
        "items": [
            {
                "entry": {
                    "key": "pdf-ref-0001",
                    "type": "article",
                    "fields": {
                        "title": "Example Paper",
                        "journal": "Example Journal",
                        "year": "2025",
                    },
                    "persons": {
                        "author": [
                            {
                                "first": ["Jane"],
                                "middle": [],
                                "prelast": [],
                                "last": ["Smith"],
                                "lineage": [],
                                "kind": "person",
                            }
                        ]
                    },
                },
                "validations": {"extraction": {"state": "complete", "diagnostics": []}},
                "pdf": {
                    "label": None,
                    "text": text,
                    "fragments": [
                        {"page": 1, "x0": 50, "top": 100, "x1": 500, "bottom": 111, "text": text}
                    ],
                    "field_evidence": {
                        "title": [{"fragment": 0, "start": 12, "end": 25}],
                        "authors": [{"fragment": 0, "start": 0, "end": 10}],
                        "venue": [{"fragment": 0, "start": 27, "end": 42}],
                        "year": [{"fragment": 0, "start": 44, "end": 48}],
                    },
                    "uris": [],
                    "diagnostics": [],
                },
            }
        ],
    }
    return copy.deepcopy(report)
