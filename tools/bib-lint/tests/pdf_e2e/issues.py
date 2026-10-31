"""Precise independently specified locator-defect assertions for PDF acceptance."""

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from pybtex.database import parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/pdf"
CONFLICT_CODES = {
    "conflicting_identifiers",
    "identifier_mismatch",
    "unverified_identifier",
    "locator_identity_mismatch",
}
MALFORMED_CASES = {
    "adv_match_arxiv_concatenated_identifiers",
    "adv_match_arxiv_double_version",
    "adv_match_arxiv_foreign_url_identifier",
}
MUTATED_FIELDS = {
    "adv_provider_split_arxiv_url": "url",
    "adv_provider_shadowed_version_pin": "url",
    "adv_provider_shadowed_journal_id": "journal",
    "adv_provider_acl_alias_conflict": "acl_id",
    "adv_provider_openreview_alias_conflict": "openreview_id",
    "adv_provider_duplicate_forum_id": "url",
    "adv_provider_pmlr_alias_conflict": "pmlr_id",
}


@lru_cache(maxsize=1)
def _sources():
    truth = json.loads((FIXTURES / "truth.json").read_text())
    entries = {
        corpus: parse_file(FIXTURES / "corpora" / (corpus + ".bib")).entries
        for corpus in {case["corpus"] for case in truth["cases"]}
    }
    return {
        case["citation_key"]: entries[case["corpus"]][case["citation_key"]]
        for case in truth["cases"]
    }


def _presentation(value):
    return re.sub(r"\\+([%{}&])", r"\1", str(value)).strip()


def _expected(issue, case):
    key = case["source_key"]
    fields = _sources()[key].fields
    if issue.get("requirement") == "typeset_nested_doi_url":
        return {"invalid_identifier"}, ["https://doi.org/" + _presentation(fields["doi"])], True
    if key in MALFORMED_CASES:
        return {"invalid_identifier"}, [_presentation(fields["eprint"])], True
    raw = _presentation(fields[MUTATED_FIELDS[key]])
    if issue["field"] == "arxiv":
        values = re.findall(r"\d{4}\.\d{4,5}(?:v\d+)?", raw)
    elif issue["field"] == "openreview" and raw.startswith("http"):
        values = parse_qs(urlsplit(raw).query)["id"]
    else:
        values = [raw]
    return CONFLICT_CODES, values, False


def _findings(correctness):
    pending = list(correctness.get("input_findings", []))
    pending.extend(
        comparison
        for method in correctness.get("methods", [])
        for comparison in method.get("comparisons", [])
    )
    while pending:
        finding = pending.pop()
        yield finding
        pending.extend(finding.get("input_findings", []))


def _atoms(value):
    if isinstance(value, str):
        yield _presentation(value)
    elif isinstance(value, dict):
        for part in value.values():
            yield from _atoms(part)
    elif isinstance(value, list):
        for part in value:
            yield from _atoms(part)


def _contains(atom, expected, exact, field):
    if field == "doi":
        atom, expected = unquote(atom).casefold(), unquote(expected).casefold()
    if exact:
        return atom == expected
    return bool(re.search(r"(?<![\w.-])" + re.escape(expected) + r"(?![\w.-])", atom))


def assert_locator_issue(item, issue, case):
    """Require a defect code and the complete specific bad input locator.

    Only issue input evidence counts. A source's found value, prose message,
    unrelated mismatch or generic extraction warning cannot discharge this rule.
    """
    codes, values, exact = _expected(issue, case)
    correctness = item["validations"]["correctness"]
    candidates = [
        finding
        for finding in _findings(correctness)
        if finding.get("field") == issue["field"]
        and finding.get("code") in codes
        and finding.get("result") in {"unknown", "mismatch"}
    ]
    assert any(
        all(
            any(
                _contains(atom, value, exact, issue["field"])
                for atom in _atoms(finding.get("input"))
            )
            for value in values
        )
        for finding in candidates
    ), (
        case["case_id"],
        "missing precise locator issue",
        issue,
        {"codes": sorted(codes), "complete_inputs": values},
        candidates,
    )
