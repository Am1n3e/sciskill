"""Local browser sessions over the existing audit, job, and evidence APIs."""

import argparse
import json
import secrets
import threading
from pathlib import Path
from xml.parsers.expat import ExpatError

from defusedxml.common import DefusedXmlException

from bib_lint.audit import run_audit
from bib_lint.viewer.agent import attach_reviews, sidecar_path
from bib_lint.viewer.data import cache_entries, load_report, pretty_xml, read_response
from bib_lint.viewer.jobs import ACTIVE
from bib_lint.viewer.presentation import metadata, reference_detail, reference_rows, summary


def start_from_command(job, owner, registry):
    """Resume original inputs and selection, without repeating a one-shot refresh."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    for option in ("--output", "--aux", "--encoding", "--key"):
        parser.add_argument(option)
    for option in ("--include-source", "--refresh", "--verbose", "--json"):
        parser.add_argument(option, action="store_true")
    args = parser.parse_args(job.command[4:])
    return registry.start(
        args.source,
        output=args.output,
        owner=owner,
        aux=args.aux,
        encoding=args.encoding,
        include_source=args.include_source,
        citation_key=args.key,
        verbose=args.verbose,
    )


class ViewerSession:
    def __init__(self, registry, report="", cache_dir=".bib-lint-cache"):
        self.registry = registry
        self.owner = secrets.token_urlsafe(24)
        self.csrf = secrets.token_urlsafe(24)
        self.report_path = ""
        self.legacy_cache = str(Path(cache_dir).absolute())
        self.cache_dir = ""
        self.agent_path = ""
        self.active_root = ""
        self.warnings = []
        self.guard = threading.RLock()
        self.select(report)

    def select(self, path):
        self.report_path = str(Path(path).absolute()) if path else ""
        root = Path(self.report_path or "report.json")
        self.cache_dir = str(root / "cache") if root.is_dir() and path else self.legacy_cache
        self.agent_path = str(
            root / "report.agent.json" if root.is_dir() and path else sidecar_path(root)
        )

    def job(self):
        active = self.registry.find(self.active_root, self.owner) if self.active_root else None
        if active and (active.state in ACTIVE or self.report_path == str(active.workspace.root)):
            return active
        return self.registry.find(self.report_path, self.owner) if self.report_path else None

    def read(self):
        report = load_report(self.report_path)
        warnings = list(self.warnings)
        try:
            warnings.extend(attach_reviews(report, self.agent_path))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            warnings.append(f"Could not load agent evidence: {exc}")
        return report, warnings

    def state(self):
        with self.guard:
            job = self.job()
            data = {
                "csrf": self.csrf,
                "report_path": self.report_path,
                "cache_dir": self.cache_dir,
                "agent_path": self.agent_path,
                "job": job.snapshot() if job else None,
                "rows": [],
                "warnings": [],
                "error": None,
                "summary": None,
                "metadata": None,
            }
            if not self.report_path:
                return data
            try:
                report, warnings = self.read()
                rows = reference_rows(report)
                data.update(
                    rows=rows,
                    warnings=warnings,
                    summary=summary(report, rows),
                    metadata=metadata(report, self.report_path),
                    audit_input=report.get("audit_input", {}),
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, FileNotFoundError) and job and job.state in ACTIVE:
                    data["loading"] = True
                else:
                    data["error"] = f"Could not load report: {exc}"
            return data

    def item(self, key):
        report, _ = self.read()
        item = next((item for item in report["items"] if item["entry"]["key"] == key), None)
        if item is None:
            raise ValueError("Citation key not found in this report. Return to All references.")
        return item

    def detail(self, key):
        with self.guard:
            data = reference_detail(self.item(key))
            try:
                data["responses"] = cache_entries(self.cache_dir, key)
            except (OSError, ValueError, KeyError) as exc:
                data.update(responses=[], cache_error=f"Cached responses unavailable: {exc}")
            return data

    def response(self, key, index):
        with self.guard:
            self.item(key)
            entries = cache_entries(self.cache_dir, key)
            if not 0 <= index < len(entries):
                raise ValueError("Cached response not found. Reload the audit.")
            entry = entries[index]
            _, text = read_response(self.cache_dir, entry)
            extension = Path(entry["path"]).suffix
            try:
                if extension == ".json":
                    text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                elif extension == ".xml":
                    text = pretty_xml(text)
            except (ValueError, ExpatError, DefusedXmlException):
                pass  # Invalid structured content is still viewable as exact source text.
            return {"entry": entry, "text": text, "verified": True}

    def action(self, payload):
        with self.guard:
            action = payload.get("action")
            handlers = {"open": self.open, "stop": self.stop, "resume": self.resume}
            if action in handlers:
                handlers[action](payload)
            elif action in {"parse", "verify", "refresh", "verify_key", "refresh_key"}:
                self.run(action, payload)
            else:
                raise ValueError("Unknown audit action")
            return self.state()

    def open(self, payload):
        path = payload.get("report") or payload.get("output")
        if not path:
            raise ValueError("Enter an existing audit directory or report file")
        load_report(path)
        self.select(path)
        self.cache_dir = payload.get("cache_dir") or self.cache_dir
        self.agent_path = payload.get("agent_path") or self.agent_path
        self.warnings = []

    def run(self, action, payload):
        job = self.job()
        if job and job.state in ACTIVE:
            raise ValueError(
                "An audit is already running; stop it and wait before starting another"
            )
        source = payload.get("bibliography")
        if not source:
            raise ValueError("Enter a local bibliography path")
        options = {"output": payload.get("output") or None, "aux": payload.get("aux") or None}
        if action == "parse":
            workspace, _, self.warnings = run_audit(source, preview=True, **options)
        else:
            key = payload.get("key") if action.endswith("_key") else None
            if action.endswith("_key") and not key:
                raise ValueError("Enter a citation key for a selected-key audit")
            job = self.registry.start(
                source,
                owner=self.owner,
                citation_key=key,
                refresh=action.startswith("refresh"),
                **options,
            )
            workspace = job.workspace
            self.active_root = str(workspace.root)
            self.warnings = []
        self.select(workspace.root)

    def stop(self, _payload):
        job = self.job()
        if job is None or job.state not in ACTIVE:
            raise ValueError("No running audit to stop")
        self.registry.stop(job)

    def resume(self, _payload):
        job = self.job()
        if job and job.state in ACTIVE:
            raise ValueError("Wait for the current audit to exit before resuming")
        if job:
            job = start_from_command(job, self.owner, self.registry)
        else:
            report, _ = self.read()
            saved = report.get("audit_input")
            if not saved:
                raise ValueError(
                    "Enter the original input path and use Verify to resume this audit"
                )
            options = {
                key: saved[key] for key in ("aux", "encoding", "include_source") if key in saved
            }
            job = self.registry.start(
                saved["path"], output=self.report_path, owner=self.owner, **options
            )
        self.active_root = str(job.workspace.root)
        self.select(job.workspace.root)
