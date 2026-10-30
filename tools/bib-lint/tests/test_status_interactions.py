"""Status precedence must hold across real verification results, not hand-built verdicts."""

from dataclasses import asdict

import pytest
from provider_support import FixtureProvider
from support import FakeClient

from bib_lint.parser import parse_string
from bib_lint.status import reference_status
from bib_lint.verification import verify_reference
from bib_lint.verification.http import LookupFailure

ISSUES = {
    "none": "",
    "url": ",url={not-a-url}",
    "venue": ",booktitle={Different Venue}",
    "secondary-id": ",acl_id={2025.acl-long.1}",
}
PAYLOAD = {
    "heading": "An Example Paper",
    "date": "2025",
    "journal": "Example Journal",
    "ids": {"doi": "10.1234/example"},
    "people": [{"given": "Jane", "family": "Smith"}, {"given": "John", "family": "Jones"}],
}


def unavailable(*_):
    raise LookupFailure("network_error", "Controlled source outage")


@pytest.mark.parametrize(
    "authors,matched_status",
    [
        ("Smith, Jane and Jones, John", "Correct"),
        ("Smith, Jane and others", "Partial match"),
        ("Smith, Sarah and Jones, John", "Invalid"),
    ],
)
@pytest.mark.parametrize("issue", ISSUES)
@pytest.mark.parametrize("source", ["found", "missing", "unavailable"])
@pytest.mark.parametrize("used", [None, True, False], ids=["usage-unknown", "used", "unused"])
@pytest.mark.parametrize("complete", [False, True], ids=["pending", "complete"])
def test_warning_and_author_status_precedence(
    authors, matched_status, issue, source, used, complete
):
    entry = asdict(
        parse_string(
            f"@article{{Example,title={{An Example Paper}},author={{{authors}}},"
            "year={2025},journal={Example Journal},doi={10.1234/example}" + ISSUES[issue] + "}"
        ).entries["Example"]
    )
    provider = FixtureProvider(
        payload=PAYLOAD if source == "found" else None,
        lookup=unavailable if source == "unavailable" else None,
    )
    result = verify_reference(entry, FakeClient(), methods=[provider])
    validations = {"correctness": {**result, "complete": complete}}
    if used is not None:
        validations["is_used"] = used
    # No source means a secondary identifier is unresolved, not independently contradictory.
    warning = issue in {"url", "venue"} or (issue == "secondary-id" and source == "found")
    assert bool(result["input_findings"]) == warning
    if source != "found":
        expected = "Needs review" if warning else "Unresolved"
    elif warning and matched_status != "Invalid":
        expected = "Needs review"
    else:
        expected = matched_status
    if not complete:
        expected = "Pending"
    if used is False:
        expected = "Skipped"
    assert reference_status(validations) == expected
