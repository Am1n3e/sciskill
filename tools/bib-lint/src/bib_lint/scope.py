"""Versioned verification eligibility, independent of paper citation usage."""

import hashlib
import json

from bib_lint.citation_keys import resolve_citation_key


def validate_outcome(method):
    if (
        not isinstance(method, dict)
        or not isinstance(method.get("name"), str)
        or method.get("status")
        not in ("found", "not_found", "ambiguous", "error", "not_applicable")
    ):
        raise ValueError("Correctness must contain structured source outcomes")
    if method["status"] == "found":
        record = method.get("found_ref")
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("identifiers", {}), dict)
            or not isinstance(record.get("authors", []), list)
            or any(not isinstance(a, dict) for a in record.get("authors", []))
        ):
            raise ValueError("Found source outcomes must contain a structured record")
    _validate_outcome_metadata(method)


def validate_report(report):
    if not isinstance(report, dict) or report.get("schema_version") not in (2, 3):
        raise ValueError("Expected a bib-lint schema version 2 or 3 report")
    if not isinstance(report.get("items"), list):
        raise ValueError("Report must contain items")
    keys = _validate_items(report)
    _validate_run(report)
    if "summary" in report and not isinstance(report["summary"], dict):
        raise ValueError("summary must be an object")
    if len({key.lower() for key in keys}) != len(keys):
        raise ValueError("Duplicate citation keys in report; each key must match exactly one entry")
    return _validate_scope(report, keys)


def eligible_items(report):
    scope = validate_report(report)
    keys = set(scope["eligible_keys"])
    return [i for i in report["items"] if i["entry"]["key"] in keys]


def selected_items(report, key=None):
    eligible = eligible_items(report)
    if key is None:
        return eligible
    resolved = resolve_citation_key(key, (i["entry"]["key"] for i in report["items"]))
    if resolved is None:
        raise ValueError(f"Citation key must match exactly one entry: {key}")
    matches = [i for i in report["items"] if i["entry"]["key"] == resolved]
    if matches[0] not in eligible:
        raise ValueError(f"Citation key is unused according to AUX: {key}")
    return matches


def fingerprint(report):
    data = {
        "version": 1,
        "scope": validate_report(report),
        "inputs": [
            {"entry": i["entry"], "is_used": i["validations"].get("is_used")}
            for i in report["items"]
        ],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _validate_outcome_metadata(method):
    for key in ("comparisons", "differences"):
        values = method.get(key, [])
        if not isinstance(values, list) or any(
            not isinstance(c, dict)
            or not isinstance(c.get("field"), str)
            or c.get("result")
            not in ("match", "mismatch", "partial_match", "unknown", "not_checked")
            for c in values
        ):
            raise ValueError("Source comparisons must contain fields and comparison results")
    for key in ("adapter_version", "display_name", "evidence_category"):
        if key in method and not isinstance(method[key], str):
            raise ValueError(f"Source {key} must be text")
    if "canonical_priority" in method and type(method["canonical_priority"]) is not int:
        raise ValueError("Source canonical_priority must be an integer")
    if "lookup_complete" in method and type(method["lookup_complete"]) is not bool:
        raise ValueError("Source lookup_complete must be boolean")
    if "lookup_provenance" in method:
        attempts = method["lookup_provenance"]
        if not isinstance(attempts, list) or any(
            not isinstance(a, dict)
            or not isinstance(a.get("strategy"), str)
            or not isinstance(a.get("scope"), str)
            or type(a.get("complete")) is not bool
            or not isinstance(a.get("diagnostic", ""), str)
            for a in attempts
        ):
            raise ValueError("Source lookup provenance must contain structured attempts")


def _validate_people(entry):
    for people in entry["persons"].values():
        if not isinstance(people, (list, tuple)):
            raise ValueError("Persons must contain lists of structured names")
        for person in people:
            if not isinstance(person, dict) or any(
                not isinstance(person.get(part, []), (list, tuple))
                or any(not isinstance(v, str) for v in person.get(part, []))
                for part in ("first", "middle", "prelast", "last", "lineage")
            ):
                raise ValueError("Name parts must be lists of text")


def _validate_input_findings(correctness):
    if "input_findings" not in correctness:
        return  # Historical reports predate local metadata validation.
    findings = correctness["input_findings"]
    if not isinstance(findings, list) or any(
        not isinstance(finding, dict)
        or any(not isinstance(finding.get(key), str) for key in ("field", "code", "message"))
        or finding.get("result") not in {"unknown", "mismatch"}
        for finding in findings
    ):
        raise ValueError("Input findings must contain structured metadata diagnostics")


def _validate_items(report):
    keys = []
    for item in report["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("validations"), dict):
            raise ValueError("Every item must contain entry and validations objects")
        entry = item.get("entry")
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("key"), str)
            or not isinstance(entry.get("fields"), dict)
            or not isinstance(entry.get("persons"), dict)
        ):
            raise ValueError("Entry must contain key, fields and persons")
        if not entry["key"] or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in entry["fields"].items()
        ):
            raise ValueError("Entry keys must be nonempty and field values must be text")
        _validate_people(entry)
        correctness = item["validations"].get("correctness")
        if correctness is not None and (
            not isinstance(correctness, dict) or not isinstance(correctness.get("methods"), list)
        ):
            raise ValueError("Correctness must contain structured source outcomes")
        if correctness is not None:
            _validate_input_findings(correctness)
            for method in correctness["methods"]:
                validate_outcome(method)
        keys.append(entry["key"])
    return keys


def _validate_run(report):
    if "verification_run" in report and not isinstance(report["verification_run"], dict):
        raise ValueError("verification_run must be an object")
    run = report.get("verification_run", {})
    if "provider_protocol_version" in run:
        if (
            type(run["provider_protocol_version"]) is not int
            or run["provider_protocol_version"] <= 0
        ):
            raise ValueError("Provider protocol version must be a positive integer")
    if "providers" in run:
        from bib_lint.verification.providers.protocol import ProviderDescriptor, RequestPolicy

        providers = run["providers"]
        if not isinstance(providers, list):
            raise ValueError("Run providers must be an ordered descriptor list")
        ids = []
        for serialized in providers:
            try:
                data = dict(serialized)
                policy = dict(data.pop("request_policy"))
                policy["backoffs"] = tuple(policy["backoffs"])
                data["allowed_hosts"] = tuple(data["allowed_hosts"])
                data["discovery_config"] = tuple(data["discovery_config"].items())
                descriptor = ProviderDescriptor(**data, request_policy=RequestPolicy(**policy))
                descriptor.validate()
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError("Invalid saved provider descriptor") from exc
            ids.append(descriptor.id)
        if len(set(ids)) != len(ids) or run.get("methods") != ids:
            raise ValueError("Run provider IDs must match methods without duplicates")


def _validate_scope(report, keys):
    if report["schema_version"] == 2:
        if any(type(i["validations"].get("is_used")) is not bool for i in report["items"]):
            raise ValueError(
                "Usage is unknown; verify the bibliography directly, optionally with --aux"
            )
        return {
            "mode": "used",
            "eligible_keys": [
                i["entry"]["key"] for i in report["items"] if i["validations"]["is_used"]
            ],
        }
    scope = report.get("verification_scope")
    if not isinstance(scope, dict) or scope.get("mode") not in ("all", "used"):
        raise ValueError("Schema 3 requires verification_scope with all or used mode")
    if scope["mode"] == "used":
        if any(type(i["validations"].get("is_used")) is not bool for i in report["items"]):
            raise ValueError("Used scope requires boolean AUX usage")
        expected = [i["entry"]["key"] for i in report["items"] if i["validations"]["is_used"]]
    else:
        if any("is_used" in i["validations"] for i in report["items"]):
            raise ValueError("All scope must leave paper usage unknown")
        expected = keys
    if scope.get("eligible_keys") != expected:
        raise ValueError("Verification scope does not match report eligibility")
    return scope
