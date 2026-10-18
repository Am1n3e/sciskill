"""Verify every entry using independently executed provider adapters."""

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bib_lint.scope import eligible_items, fingerprint, selected_items, validate_report
from bib_lint.status import reference_status, source_status
from bib_lint.storage import report_lock, report_paths
from bib_lint.storage import write_json as _write_json
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.matching import select_result
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import Applicability, LookupQuery, LookupResult
from bib_lint.verification.providers.registry import validate_registry


def _attempt_data(attempt):
    data = asdict(attempt)
    data["candidate_urls"] = list(attempt.candidate_urls)
    return data


def _source_result(provider, query, context):
    descriptor = provider.descriptor
    applicable = provider.applicability(query)
    if not isinstance(applicable, Applicability):
        raise ValueError("Provider must return Applicability")
    applicable.validate()
    if applicable.state != "applicable":
        result = select_result(descriptor.id, query.as_record(), [])
        result["reason"] = applicable.reason
        if applicable.state == "inapplicable":
            result["status"] = "not_applicable"
        else:
            result.update(
                status="error", error={"code": "incomplete_search", "message": applicable.reason}
            )
        result["lookup_provenance"] = [
            {
                "strategy": s,
                "scope": descriptor.display_name,
                "complete": False,
                "diagnostic": applicable.reason,
            }
            for s in applicable.strategies
        ]
        return result
    lookup = provider.lookup(query, context)
    if not isinstance(lookup, LookupResult):
        raise ValueError("Provider must return LookupResult")
    lookup.validate()
    if len(lookup.candidates) > descriptor.request_policy.max_candidates:
        raise LookupFailure("incomplete_search", "Candidate budget exceeded")
    records = [c.as_record() for c in lookup.candidates]
    result = select_result(descriptor.id, query.as_record(), records)
    result["lookup_provenance"] = [_attempt_data(a) for a in lookup.attempts]
    result["lookup_complete"] = lookup.complete

    def authoritative(record):
        if descriptor.evidence_category == "preprint_archive":
            return record.get("record_type") == "preprint"
        return record.get("record_type") == "publication" and record.get("publication_status") in {
            "accepted",
            "published",
        }

    result["authority"] = (
        authoritative(result["found_ref"])
        if result.get("found_ref")
        else any(authoritative(r) for r in records)
    )
    if not lookup.complete:
        result.update(
            status="error",
            authority=False,
            found_ref=None,
            comparisons=[],
            differences=[],
            candidates=records,
            error={"code": "incomplete_search", "message": lookup.diagnostic},
        )
    return result


def verify_reference(
    entry: dict,
    client: MetadataClient,
    *,
    methods=None,
    previous=None,
    progress=None,
    checkpoint=None,
) -> dict:
    registry = validate_registry(METHODS if methods is None else methods)
    query = LookupQuery.from_entry(entry)
    results = []
    saved = {m["name"]: m for m in (previous or [])}
    for name, provider in registry.items():
        if name in saved and saved[name]["status"] != "error":
            results.append(saved[name])
            if progress:
                progress(f"  {name}: Resumed ({source_status(saved[name]['status'])})")
            continue
        if progress:
            progress(f"  {name}: Fetching ...")
        client.progress = (
            (lambda message, name=name: progress(f"  {name}: {message}")) if progress else None
        )
        client.citation_key = entry.get("key", "_unknown")
        client.method = name
        start = len(client.evidence)
        context = RequestContext(client, provider.descriptor, query.citation_key)
        result = _execute_provider(name, provider, query, context)
        result.update(
            adapter_version=provider.descriptor.adapter_version,
            display_name=provider.descriptor.display_name,
            evidence_category=provider.descriptor.evidence_category,
            canonical_priority=provider.descriptor.canonical_priority,
        )
        result["requests"] = client.evidence[start:]
        result["checked_at"] = datetime.now(UTC).isoformat()
        results.append(result)
        if checkpoint:
            checkpoint(copy.deepcopy(results))
        if progress:
            _source_progress(name, result, progress)
    client.progress = None
    return build_consensus(results)


_validate_report = validate_report


def _fingerprint(report):
    inputs = [
        {"entry": i["entry"], "is_used": i["validations"].get("is_used")} for i in report["items"]
    ]
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def _totals(report):
    totals = {
        "correct": 0,
        "incorrect": 0,
        "unresolved": 0,
        "partial_match": 0,
        "needs_review": 0,
        "method_errors": 0,
        "skipped_unused": 0,
    }
    for item in report["items"]:
        if report.get("verification_scope", {}).get("mode") != "all" and not item[
            "validations"
        ].get("is_used"):
            totals["skipped_unused"] += 1
            continue
        result = item["validations"].get("correctness")
        if result is None or result.get("complete") is False:
            continue
        status = reference_status(item["validations"])
        key = "incorrect" if status == "Invalid" else status.lower().replace(" ", "_")
        totals[key] += 1
        totals["method_errors"] += sum(m["status"] == "error" for m in result["methods"])
    return totals


def verify_file(
    path: str | Path,
    *,
    output: str | Path | None = None,
    cache_dir: str | Path = ".bib-lint-cache",
    refresh=False,
    verbose=False,
    citation_key: str | None = None,
    progress: Callable[[str], None] | None = None,
    client=None,
    methods=None,
) -> tuple[Path, dict]:
    source = Path(path)
    destination, checkpoint = report_paths(Path(output) if output is not None else source)
    registry = validate_registry(METHODS if methods is None else methods)
    with report_lock(destination):
        # A finished run has renamed the temporary file; accept the original command again.
        readable = source
        if not source.exists() and source.resolve() in {
            destination.resolve(),
            checkpoint.resolve(),
        }:
            readable = checkpoint if checkpoint.exists() else destination
        report = json.loads(readable.read_text(encoding="utf-8"))
        _validate_report(report)
        if checkpoint.exists() and checkpoint.resolve() != readable.resolve():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            _validate_report(saved)
            if _fingerprint(saved) != _fingerprint(report):
                raise ValueError(f"Checkpoint belongs to different inputs: {checkpoint}")
            report = saved
        return verify_report_locked(
            report,
            destination,
            checkpoint,
            cache_dir=cache_dir,
            refresh=refresh,
            verbose=verbose,
            citation_key=citation_key,
            progress=progress,
            client=client,
            methods=registry,
        )


def verify_report_locked(
    report,
    destination,
    checkpoint,
    *,
    cache_dir,
    refresh=False,
    verbose=False,
    citation_key=None,
    progress=None,
    client=None,
    methods=None,
):
    """Execute under the caller's report lock; never reacquire it."""
    registry = validate_registry(METHODS if methods is None else methods)
    selected = selected_items(report, citation_key)
    used = eligible_items(report)
    _prepare_run(report, registry, selected, refresh)
    _write_json(checkpoint, report)
    owned = client is None
    client = client or MetadataClient(Path(cache_dir), refresh=refresh, verbose=verbose)
    if verbose:
        client.verbose = True
    try:
        for index, item in enumerate(selected, 1):
            if progress:
                progress(f"Verifying {index}/{len(selected)}: {item['entry'].get('key', '?')}")
            previous = item["validations"].get("correctness", {}).get("methods", [])

            def save_method(results, item=item, previous=previous):
                merged = {m["name"]: m for m in previous}
                merged.update({m["name"]: m for m in results})
                results = [merged[name] for name in registry if name in merged]
                result = build_consensus(results)
                result["complete"] = len(results) == len(registry)
                if not result["complete"]:
                    result["is_correct"] = None
                item["validations"]["correctness"] = result
                report.setdefault("summary", {})["verification"] = _totals(report)
                _write_json(checkpoint, report)

            result = verify_reference(
                item["entry"],
                client,
                methods=registry,
                previous=previous,
                progress=progress,
                checkpoint=save_method,
            )
            result["complete"] = True
            item["validations"]["correctness"] = result
            report.setdefault("summary", {})["verification"] = _totals(report)
            _write_json(checkpoint, report)
            if progress:
                state = reference_status(item["validations"]).lower()
                consensus = result["consensus"]
                progress(f"  status: {state}")
                progress(f"  found: {consensus['records_found']}/{consensus['applicable']}")
                progress(f"  consensus: {consensus['display']}")
    finally:
        if owned:
            client.close()
    totals = _totals(report)
    report.setdefault("summary", {})["verification"] = totals
    complete = all(
        item["validations"].get("correctness", {}).get("complete", False) for item in used
    )
    report["verification_run"]["complete"] = complete
    _write_json(checkpoint, report)
    if complete:
        checkpoint.replace(destination)
    elif progress:
        progress("Other eligible references remain pending; checkpoint retained.")
    return destination if complete else checkpoint, totals


def _execute_provider(name, provider, query, context):
    try:
        result = _source_result(provider, query, context)
    except OSError:
        # Evidence persistence failures are execution errors, not provider findings.
        raise
    except Exception as exc:
        # One provider failing must not prevent other independent lookups.
        code = exc.code if isinstance(exc, LookupFailure) else "invalid_response"
        result = {
            "name": name,
            "status": "not_found" if code == "not_found" else "error",
            "found_ref": None,
            "agrees_with_consensus": None,
            "differences": [],
        }
        if code != "not_found":
            result["error"] = {
                "code": code,
                "message": str(exc) if isinstance(exc, LookupFailure) else type(exc).__name__,
            }
        result["lookup_provenance"] = [
            _attempt_data(a) for a in getattr(context, "lookup_attempts", ())
        ]
        candidates = [c.as_record() for c in getattr(context, "retrieved_candidates", ())]
        if candidates:
            result["candidates"] = candidates
    return result


def _source_progress(name, result, progress):
    error = result.get("error", {})
    label = source_status(result["status"])
    if result["status"] == "error":
        label += f": {error.get('code', 'unknown')}"
    if result["status"] == "error" and error.get("message"):
        label += f" — {error['message']}"
    progress(f"  {name}: {label}")


def _prepare_run(report, registry, selected, refresh):
    input_hash = _fingerprint(report) if report["schema_version"] == 2 else fingerprint(report)
    run = report.get("verification_run")
    expected = {
        "fingerprint": input_hash,
        "methods": list(registry),
        "policy_version": 5,
        "orchestration_version": 2,
        "provider_protocol_version": 1,
        "providers": [p.descriptor.serialize() for p in registry.values()],
    }
    reusable = run and all(run.get(key) == value for key, value in expected.items())
    if not reusable or refresh:
        for item in report["items"] if not reusable else selected:
            item["validations"].pop("correctness", None)
    report["verification_run"] = {**expected, "complete": False}
