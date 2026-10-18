"""Local audit directories and the single parse/resume/verification boundary."""

import json
from dataclasses import dataclass
from pathlib import Path

from bib_lint.aux import read_aux
from bib_lint.parser import parse_file
from bib_lint.scope import eligible_items, fingerprint, selected_items, validate_report
from bib_lint.status import reference_status
from bib_lint.storage import report_lock, write_json
from bib_lint.verification import _fingerprint, verify_report_locked
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.registry import validate_registry
from bib_lint.workflow import _protect


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def for_input(cls, source, output=None):
        source = Path(source).absolute()
        stem = source.stem.removesuffix(".tmp")
        root = Path(output) if output is not None else source.with_name(stem + ".bib-lint")
        root = root.absolute()
        if root.exists() and not root.is_dir():
            raise ValueError(f"Output must be a directory: {root}")
        return cls(root)

    @property
    def final(self):
        return self.root / "report.json"

    @property
    def checkpoint(self):
        return self.root / "report.tmp.json"

    @property
    def cache(self):
        return self.root / "cache"

    def active(self):
        return self.checkpoint if self.checkpoint.exists() else self.final


def prepare_input(source, *, aux=None, encoding=None, include_source=False):
    source = Path(source).absolute()
    warnings = []
    inputs = [source]
    if source.suffix.lower() == ".bib":
        bib = parse_file(source, encoding=encoding or "utf-8")
        citations = read_aux(aux, encoding=encoding or "utf-8") if aux is not None else None
        if citations:
            inputs.extend(citations.files)
            known = {key.casefold() for key in bib.entries}
            missing = sorted(k for k in citations.keys if k.casefold() not in known | {"*"})
            if missing:
                warnings.append("Missing citation keys: " + ", ".join(missing))
        report = bib.to_dict(
            include_source=include_source, used_keys=citations.keys if citations else None
        )
        report["schema_version"] = 3
        report["verification_scope"] = {
            "mode": "used" if citations else "all",
            "eligible_keys": [
                i["entry"]["key"]
                for i in report["items"]
                if citations is None or i["validations"].get("is_used")
            ],
        }
        report["audit_input"] = {
            "path": str(source),
            "aux": str(Path(aux).absolute()) if aux is not None else None,
            "encoding": encoding or "utf-8",
            "include_source": include_source,
        }
    elif source.suffix.lower() == ".json":
        if aux is not None or encoding is not None or include_source:
            raise ValueError(
                "--aux, --encoding and --include-source apply only to bibliography input"
            )
        report = json.loads(source.read_text(encoding="utf-8"))
        scope = validate_report(report)
        if report["schema_version"] == 2:
            old_hash = _fingerprint(report)
            report["schema_version"] = 3
            report["verification_scope"] = scope
            run = report.get("verification_run", {})
            if run.get("fingerprint") == old_hash:
                run["fingerprint"] = fingerprint(report)
                # Only the entry/scope fingerprint changes during schema conversion.
                # Provider and orchestration versions still govern decision reuse.
        report["audit_input"] = {"path": str(source), "aux": None}
    else:
        raise ValueError("Input must be a .bib bibliography or .json report")
    validate_report(report)
    report["audit_warnings"] = warnings
    return report, inputs, warnings


def run_audit(
    source,
    *,
    output=None,
    aux=None,
    encoding=None,
    include_source=False,
    citation_key=None,
    refresh=False,
    verbose=False,
    preview=False,
    progress=None,
    client=None,
    methods=None,
):
    """Validate first; own one stable lock through initialization and promotion."""
    registry = validate_registry(METHODS if methods is None else methods)
    workspace = Workspace.for_input(source, output)
    report, inputs, warnings = prepare_input(
        source, aux=aux, encoding=encoding, include_source=include_source
    )
    selected_items(report, citation_key)  # Invalid keys must never replace saved work.
    for target in (
        workspace.final,
        workspace.checkpoint,
        Path(str(workspace.final) + ".lock"),
        workspace.cache / "checksum.json",
        workspace.cache / "checksum.json.lock",
    ):
        _protect(target, inputs)
    # Symlinked managed cache directories could redirect writes into another audit.
    if workspace.cache.is_symlink():
        raise ValueError(f"Cache directory must not be a symlink: {workspace.cache}")
    workspace.root.mkdir(parents=True, exist_ok=True)
    with report_lock(workspace.final):
        if workspace.active().exists():
            saved = json.loads(workspace.active().read_text(encoding="utf-8"))
            validate_report(saved)
            if fingerprint(saved) != fingerprint(report):
                raise ValueError(
                    "Workspace belongs to different inputs; choose a new output directory"
                )
            report = saved
        if preview:
            if not workspace.active().exists():
                write_json(workspace.checkpoint, report)
        else:
            workspace.cache.mkdir(exist_ok=True)
            verify_report_locked(
                report,
                workspace.final,
                workspace.checkpoint,
                cache_dir=workspace.cache,
                refresh=refresh,
                verbose=verbose,
                citation_key=citation_key,
                progress=progress,
                client=client,
                methods=registry,
            )
    return workspace, report, warnings


def audit_summary(report):
    eligible = eligible_items(report)
    complete = [
        i for i in eligible if i["validations"].get("correctness", {}).get("complete", False)
    ]
    counts = dict.fromkeys(("correct", "invalid", "unresolved", "partial_match", "needs_review"), 0)
    for item in complete:
        label = reference_status(item["validations"]).lower().replace(" ", "_")
        counts[label] += 1
    used = None if validate_report(report)["mode"] == "all" else len(eligible)
    return {
        "total": len(report["items"]),
        "eligible": len(eligible),
        "completed": len(complete),
        "pending": len(eligible) - len(complete),
        "used": used,
        "unused": None if used is None else len(report["items"]) - used,
        **counts,
        "source_failures": sum(
            m.get("status") == "error"
            for i in eligible
            for m in i["validations"].get("correctness", {}).get("methods", [])
        ),
    }
