"""Expose nearby rejected PDF candidates without claiming a resolved paper identity."""

from bib_lint.pdf_presentation import _author_presentation
from bib_lint.verification.matching import compare_fields, input_record, normalize, title_similarity


def _named_authors(authors):
    return bool(authors) and all(
        normalize(person.get("family")) not in {"", "others"} and person.get("kind") != "others"
        for person in authors
    )


def _compatible_authors(item, original, candidate):
    left, right = original.get("authors", []), candidate.get("authors", [])
    if len(left) != len(right) or not _named_authors(left) or not _named_authors(right):
        return False
    alternate = _author_presentation(item, left, right)
    if any(
        normalize(a["family"]) != normalize(b["family"])
        for a, b in zip(alternate, right, strict=True)
    ):
        return False
    comparison = next(
        c
        for c in compare_fields({"authors": alternate}, {"authors": right})
        if c["field"] == "authors"
    )
    return comparison["result"] in {"match", "unknown"}


def _nearby(item, original, candidate):
    return (
        original.get("title")
        and candidate.get("title")
        and normalize(original["title"]) != normalize(candidate["title"])
        and title_similarity(original, candidate) >= 0.88
        and original.get("year")
        and candidate.get("year")
        and normalize(original["year"]) == normalize(candidate["year"])
        and _compatible_authors(item, original, candidate)
    )


def candidate_findings(item, methods):
    """Only already-retrieved rejected records may support a PDF review finding."""
    original = input_record(item["entry"])
    findings, seen = [], set()
    for method in methods:
        if method.get("status") != "not_found":
            continue
        for candidate in method.get("rejected_candidates", []):
            title = normalize(candidate.get("title"))
            if title in seen or not _nearby(item, original, candidate):
                continue
            seen.add(title)
            findings.append(
                {
                    "field": "title",
                    "code": "candidate_title_discrepancy",
                    "result": "unknown",
                    "input": original["title"],
                    "found": candidate["title"],
                    "message": (
                        "A nearby retrieved candidate has a different title; identity unconfirmed"
                    ),
                }
            )
    return findings
