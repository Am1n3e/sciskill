"""Opt-in experiment: resolve supplied paper URLs before source discovery.

This does not change the production audit or its multi-source consensus policy.
"""

from dataclasses import replace
from time import sleep
from urllib.parse import urlsplit

from huey.exceptions import TaskException

from bib_lint.verification.input_checks import (
    input_findings,
    invalid_url_characters,
    locator,
    unverified_locator_findings,
    url_locators,
)
from bib_lint.verification.matching import compare_fields, select_result
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import LookupQuery


def route_url(entry, providers=METHODS):
    url = entry.get("fields", {}).get("url", "")
    if invalid_url_characters(url):
        return None
    locators = url_locators(url)
    if len(locators) != 1:
        return None
    source, value = locators[0]
    name = "acl_anthology" if source == "acl" else source
    provider = providers.get(name)
    if (
        provider
        and locator(source, value)
        and urlsplit(url).hostname in provider.descriptor.allowed_hosts
    ):
        return name
    return None


def _retrieval_query(entry, phase):
    original = LookupQuery.from_entry(entry)
    if phase == "direct":
        return LookupQuery.from_entry({"key": entry["key"], "fields": {"url": original.input_url}})
    if phase != "search":
        raise ValueError(f"Unknown lookup phase: {phase}")
    # Discovery must not re-fetch a locator that the direct phase already tried.
    return replace(
        original,
        input_url="",
        identifiers=(),
        fields=tuple((k, v) for k, v in original.fields if k == "volume"),
    )


def _resolved_status(query, record, comparisons):
    if any(c["result"] == "mismatch" for c in comparisons):
        return "mismatch"
    authoritative = record.get("publication_status") in {"accepted", "published"}
    if (
        not authoritative
        or query.record_type != record.get("record_type")
        or any(c["result"] == "unknown" for c in comparisons)
    ):
        return "needs_review"
    return "verified"


def lookup_entry(entry, provider, phase, client):
    """Retrieve without discovery in direct mode; compare against untouched input."""
    query = LookupQuery.from_entry(entry)
    context = RequestContext(client, provider.descriptor, query.citation_key)
    lookup = provider.lookup(_retrieval_query(entry, phase), context)
    lookup.validate()
    records = [candidate.as_record() for candidate in lookup.candidates]
    result = {
        "outcome": "unresolved",
        "provider": provider.descriptor.id,
        "phase": phase,
        "records": records,
        "requests": context.evidence,
        "diagnostic": lookup.diagnostic,
        "input_findings": input_findings(dict(query.fields)),
    }
    if not lookup.complete:
        return result
    if phase == "search":
        selected = select_result(provider.descriptor.id, query.as_record(), records)
        record = selected.get("found_ref")
    else:
        record = records[0] if len(records) == 1 else None
    if not record or not all(record.get(f) for f in ("title", "authors", "year")):
        return result
    comparisons = compare_fields(query.as_record(), record)
    result["input_findings"].extend(
        unverified_locator_findings(
            dict(query.fields),
            [{"status": "found", "authority": True, "found_ref": record}],
        )
    )
    result.update(
        outcome="resolved",
        status=_resolved_status(query, record, comparisons + result["input_findings"]),
        record=record,
        comparisons=comparisons,
    )
    return result


def _plan(entry, providers):
    direct = route_url(entry, providers)
    if direct:
        yield direct, "direct"
        yield direct, "search"
    for name in providers:
        if name != direct:
            yield name, "search"


def _finished(future, provider, phase):
    try:
        result = future.get()
    except TaskException as exc:
        result = {"outcome": "unresolved", "error": str(exc)}
    if result["outcome"] == "fatal":
        raise RuntimeError(result["error"])
    return {**result, "provider": provider, "phase": phase}


def run_entries(entries, queues):
    """Submit one initial task per reference, then expand only unresolved lookups."""
    keys = [entry["key"] for entry in entries]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate citation keys")
    pending, completed = {}, {}
    for entry in entries:
        plan = iter(_plan(entry, queues.providers))
        provider, phase = next(plan)
        future = queues.submit(entry, provider, phase)
        pending[entry["key"]] = (entry, plan, future, provider, phase, [])
    while pending:
        progressed = False
        for key, (entry, plan, future, provider, phase, history) in list(pending.items()):
            if not future.is_ready():
                continue
            progressed = True
            result = _finished(future, provider, phase)
            history.append(result)
            following = next(plan, None) if result["outcome"] != "resolved" else None
            if following:
                provider, phase = following
                future = queues.submit(entry, provider, phase)
                pending[key] = (entry, plan, future, provider, phase, history)
            else:
                completed[key] = {**result, "attempts": history}
                del pending[key]
        if not progressed:
            sleep(0.01)
    return {key: completed[key] for key in keys}
