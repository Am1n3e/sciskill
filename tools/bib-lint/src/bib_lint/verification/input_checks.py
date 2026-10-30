"""Retain independently supplied locators and detect input contradictions.

Routing can choose one locator; verification must still assess the other supplied
locators. These checks never copy input metadata into a retrieved source record.
"""

import re
from urllib.parse import parse_qs, unquote, urlsplit

from bib_lint.verification.matching import arxiv_id, doi, normalize

ARXIV_TOKEN = r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v[1-9]\d*)?"
ALIASES = {
    "arxiv": ("arxiv", "arxiv_id"),
    "doi": ("doi",),
    "pmlr": ("pmlr", "pmlr_id"),
    "jmlr": ("jmlr", "jmlr_id"),
    "acl": ("acl", "acl_id", "anthology_id", "acl_anthology"),
    "neurips": ("neurips", "neurips_id"),
    "openreview": ("openreview", "openreview_id", "forum"),
}
HOSTS = {
    "arxiv.org": "arxiv",
    "export.arxiv.org": "arxiv",
    "doi.org": "doi",
    "dx.doi.org": "doi",
    "proceedings.mlr.press": "pmlr",
    "jmlr.org": "jmlr",
    "www.jmlr.org": "jmlr",
    "aclanthology.org": "acl",
    "openreview.net": "openreview",
    "api.openreview.net": "openreview",
    "api2.openreview.net": "openreview",
    "proceedings.neurips.cc": "neurips",
    "papers.nips.cc": "neurips",
    "datasets-benchmarks-proceedings.neurips.cc": "neurips",
}


def strict_arxiv(value):
    value = re.sub(r"^arxiv:\s*", "", str(value).strip(), flags=re.I)
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "arxiv.org",
            "export.arxiv.org",
        }:
            return None
        if not safe_url(parsed):
            return None
        match = re.fullmatch(r"/(?:abs|pdf)/(.+?)(?:\.pdf)?/?", parsed.path)
        value = match[1] if match else ""
    return value if re.fullmatch(ARXIV_TOKEN, value, re.I) else None


def safe_url(parsed):
    try:
        return not parsed.username and not parsed.password and parsed.port in {None, 80, 443}
    except ValueError:
        return False


def locator(provider, value):
    if provider == "arxiv":
        return strict_arxiv(value)
    if provider == "doi":
        result = doi(value)
        return result if re.fullmatch(r"10\.\d{4,9}/\S+", result) else None
    if provider == "jmlr":
        from bib_lint.verification.providers.jmlr import jmlr_identifier

        return jmlr_identifier(value)
    value = str(value).strip()
    if provider == "pmlr":
        pdf = re.fullmatch(r"(v\d+)/([\w.-]+)/\2\.pdf", value)
        if pdf:
            return f"{pdf[1]}/{pdf[2]}"
    if provider == "neurips":
        pdf = re.fullmatch(
            r"((?:paper_files/paper|paper)/\d{4})/file/(.+)-Paper(-[^/]+)?\.pdf", value
        )
        if pdf:
            return f"{pdf[1]}/hash/{pdf[2]}-Abstract{pdf[3] or ''}"
    patterns = {
        "pmlr": r"v\d+/[\w.-]+",
        "acl": r"(?:\d{4}\.[a-z][a-z0-9_-]*\.\d+|[A-Z]\d{2}-\d{4})",
        "neurips": r"(?:paper_files/paper|paper)/\d{4}/(?:hash/)?[\w.-]+",
        "openreview": r"[A-Za-z0-9_-]+",
    }
    if provider in {"pmlr", "acl", "neurips"}:
        value = re.sub(r"\.(?:html|pdf|bib)$", "", value)
    return value if re.fullmatch(patterns[provider], value) else None


def url_locators(value):
    try:
        parsed = urlsplit(value)
    except ValueError:
        return []
    provider = HOSTS.get(parsed.hostname)
    if not provider or parsed.scheme not in {"http", "https"} or not safe_url(parsed):
        return []
    if provider == "openreview":
        return [
            (provider, identifier)
            for identifier in parse_qs(parsed.query, keep_blank_values=True).get("id", [])
        ]
    if provider in {"arxiv", "doi", "jmlr"}:
        return [(provider, value)]
    return [(provider, unquote(parsed.path.strip("/")))]


def supplied_locators(fields):
    values = []
    for provider, aliases in ALIASES.items():
        values.extend((provider, alias, fields[alias]) for alias in aliases if fields.get(alias))
    for provider, value in url_locators(fields.get("url", "")):
        values.append((provider, "url", value))
    eprint = fields.get("eprint")
    prefix = normalize(fields.get("archiveprefix"))
    if eprint:
        provider = prefix if prefix in ALIASES else "arxiv" if arxiv_id(eprint) else None
        if provider:
            values.append((provider, "eprint", eprint))
    journal = fields.get("journal", "")
    if "arxiv" in journal.casefold():
        for match in re.finditer(ARXIV_TOKEN, journal, re.I):
            values.append(("arxiv", "journal", match[0]))
    return values


def compatible(provider, a, b):
    if a == b:
        return True
    if provider != "arxiv":
        return False
    av, bv = re.search(r"v\d+$", a), re.search(r"v\d+$", b)
    return not (av and bv) and re.sub(r"v\d+$", "", a) == re.sub(r"v\d+$", "", b)


def finding(field, inputs, code, message, *, result="unknown", found=None):
    return {
        "field": field,
        "input": inputs,
        "found": found,
        "result": result,
        "code": code,
        "message": message,
    }


def identifier_findings(fields, found):
    groups, findings = {}, []
    for provider, field, raw in supplied_locators(fields):
        value = locator(provider, raw)
        if value is None:
            findings.append(
                finding(
                    provider,
                    {field: raw},
                    "invalid_identifier",
                    "The complete supplied locator is not a valid identifier",
                )
            )
        else:
            groups.setdefault(provider, []).append((field, value))
    for provider, values in groups.items():
        inputs = [{"field": field, "identifier": value} for field, value in values]
        if any(not compatible(provider, a[1], b[1]) for a in values for b in values):
            findings.append(
                finding(
                    provider,
                    inputs,
                    "conflicting_identifiers",
                    "Supplied locators identify different records or versions",
                )
            )
        other = found.get("identifiers", {}).get(provider)
        # URL-only provider locators guide retrieval. Explicit alias fields are
        # verified against their own source, without requiring cross-source IDs.
        checked = provider in {"doi", "arxiv"} or any(f != "url" for f, _ in values)
        if other and checked:
            other = locator(provider, other) or other
            if any(not compatible(provider, value, other) for _, value in values):
                findings.append(
                    finding(
                        provider,
                        inputs,
                        "identifier_mismatch",
                        "A supplied locator differs from the retrieved record",
                        result="mismatch",
                        found=other,
                    )
                )
    return findings


def venue_findings(fields):
    journal, booktitle = fields.get("journal"), fields.get("booktitle")
    if not journal or not booktitle or normalize(journal) == normalize(booktitle):
        return []
    from bib_lint.verification.matching import is_arxiv_venue

    if is_arxiv_venue(journal) and is_arxiv_venue(booktitle):
        return []
    return [
        finding(
            "venue",
            {"journal": journal, "booktitle": booktitle},
            "conflicting_venues",
            "journal and booktitle supply different venues",
        )
    ]


def apply_input_checks(comparisons, original, found):
    fields = original.get("input_fields", {})
    additional = identifier_findings(fields, found) + venue_findings(fields)
    for issue in additional:
        prior = next((c for c in comparisons if c["field"] == issue["field"]), None)
        if prior is None:
            comparisons.append(issue)
        else:
            details = prior.get("input_findings", []) + [issue.copy()]
            if prior["result"] == "mismatch" and issue["result"] != "mismatch":
                prior["input_findings"] = details
                prior.setdefault("code", issue["code"])
                prior.setdefault("message", issue["message"])
            else:
                update = dict(issue)
                if issue["result"] == "unknown" and issue["found"] is None:
                    update["found"] = prior.get("found")
                prior.update(update, input_findings=details)
    return comparisons


def input_findings(fields):
    """Checks supported by the input itself, even when no source is available."""
    return identifier_findings(fields, {}) + venue_findings(fields) + url_findings(fields)


def url_findings(fields):
    value = fields.get("url", "").strip()
    if not value:
        return []
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname and safe_url(parsed)
    except ValueError:
        valid = False
    if valid:
        return []
    return [
        finding("url", value, "invalid_url", "The supplied URL must be an absolute HTTP(S) URL")
    ]


def unverified_locator_findings(fields, methods):
    """A verified primary must not hide an unverified secondary scholarly locator."""
    if not any(m["status"] == "found" and m.get("authority") for m in methods):
        return []
    groups = {}
    for provider, field, raw in supplied_locators(fields):
        value = locator(provider, raw)
        if value and provider != "doi":
            groups.setdefault(provider, []).append((field, value))
    findings = []
    for provider, values in groups.items():
        verified = [
            locator(provider, identifier) or identifier
            for method in methods
            if method.get("found_ref")
            if (identifier := method["found_ref"].get("identifiers", {}).get(provider))
        ]
        missing = [
            (field, value)
            for field, value in values
            if not any(compatible(provider, value, identifier) for identifier in verified)
        ]
        if missing:
            findings.append(
                finding(
                    provider,
                    [dict(field=f, identifier=v) for f, v in missing],
                    "unverified_identifier",
                    "This supplied locator was not verified against the cited paper",
                )
            )
    return findings
