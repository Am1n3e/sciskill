"""Local PDF reference extraction, isolated from source lookup and audit writes."""

import hashlib
import json
import math
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

PARSER_VERSION = "1"
DEFAULT_LIMITS = {
    "max_bytes": 32 * 1024 * 1024,
    "max_pages": 200,
    "max_decoded_bytes": 64 * 1024 * 1024,
    "max_text_chars": 1_000_000,
    "max_references": 3000,
    "max_seconds": 60,
}


class PDFExtractionError(ValueError):
    """A bounded, actionable failure before any scholarly-source request."""

    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or [{"code": "pdf_extraction_failed", "message": message}]


def _read(path, limits):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(limits["max_bytes"] + 1)
    if len(raw) > limits["max_bytes"]:
        raise PDFExtractionError("PDF exceeds max_bytes resource limit")
    if not raw.startswith(b"%PDF-"):
        raise PDFExtractionError("Input is empty or is not a PDF document")
    return raw


def _identity(raw, limits):
    return {
        "document_sha256": hashlib.sha256(raw).hexdigest(),
        "extractor": {"id": "pdfplumber", "version": version("pdfplumber")},
        "parser": {"id": "bib-lint-local", "version": PARSER_VERSION},
        "settings": limits.copy(),
    }


def extraction_identity(path):
    return _identity(_read(path, DEFAULT_LIMITS), DEFAULT_LIMITS)


def extract_pdf(path, *, limits=None):
    """Parse a byte snapshot in a bounded local worker; no service or network involved."""
    if limits is not None and not isinstance(limits, dict):
        raise PDFExtractionError("PDF resource limits must be a settings object")
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    if set(limits) != set(DEFAULT_LIMITS) or any(
        type(v) not in (int, float)
        or not math.isfinite(v)
        or not 0 < v < sys.maxsize
        or (k != "max_seconds" and type(v) is not int)
        for k, v in limits.items()
    ):
        raise PDFExtractionError("PDF resource limits must be positive numbers")
    raw = _read(path, limits)
    command = [sys.executable, "-m", "bib_lint.pdf_input.worker", json.dumps(limits)]
    try:
        result = subprocess.run(
            command, input=raw, capture_output=True, timeout=limits["max_seconds"]
        )
    except subprocess.TimeoutExpired as error:
        raise PDFExtractionError("PDF extraction exceeds max_seconds resource limit") from error
    if result.returncode or not result.stdout:
        raise PDFExtractionError("PDF parser worker failed or exceeded its resource limit")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, UnicodeError) as error:
        raise PDFExtractionError("PDF parser produced an invalid extraction result") from error
    if not isinstance(payload, dict):
        raise PDFExtractionError("PDF parser produced an invalid extraction result")
    if "error" in payload:
        raise PDFExtractionError(str(payload["error"]), payload.get("diagnostics"))
    try:
        return _complete_payload(payload, path, raw, limits)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise PDFExtractionError(
            "PDF parser produced an invalid extraction result or evidence"
        ) from error


def _complete_payload(payload, path, raw, limits):
    from bib_lint.pdf_evidence import seal_extraction
    from bib_lint.scope import validate_report

    identity = _identity(raw, limits)
    payload["extraction"].update({k: identity[k] for k in ("extractor", "parser", "settings")})
    payload["extraction"]["document"].update(
        name=Path(path).name, sha256=identity["document_sha256"]
    )
    payload["source"] = {"name": str(Path(path).absolute()), "sha256": identity["document_sha256"]}
    seal_extraction(payload)
    validate_report(payload)
    return payload
