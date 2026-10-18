"""Two public commands with a separate, versioned final-result stream."""

import argparse
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from bib_lint.audit import Workspace, audit_summary, run_audit
from bib_lint.scope import validate_report


class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)


def arguments(prog="bib-lint"):
    parser = Parser(prog=prog, description="Audit local bibliography metadata.")
    try:
        package_version = version("bib-lint")
    except PackageNotFoundError:
        package_version = version("sciskill")
    parser.add_argument("--version", action="version", version=f"bib-lint {package_version}")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Parse and verify a bibliography or import JSON")
    verify.add_argument("path", help="Input .bib or .json file (never modified)")
    verify.add_argument("--aux", type=Path, help="Compiled AUX: verify only cited entries")
    verify.add_argument(
        "-o", "--output", type=Path, help="Audit directory (default: <stem>.bib-lint)"
    )
    verify.add_argument("--key", help="Verify one eligible citation key (case-insensitive)")
    verify.add_argument("--refresh", action="store_true", help="Fetch selected sources again")
    verify.add_argument("--json", action="store_true", help="Emit one final JSON object on stdout")
    verify.add_argument("--encoding", help="BibTeX/AUX encoding (default: utf-8)")
    verify.add_argument("--include-source", action="store_true", help="Include decoded BibTeX text")
    verify.add_argument("--verbose", action="store_true", help="Redacted HTTP details on stderr")
    view = commands.add_parser("view", help="Open local workflow controls and audit evidence")
    view.add_argument("path", nargs="?", help="Audit directory or legacy report file")
    view.add_argument("--port", type=int, default=8501)
    view.add_argument("--no-browser", action="store_true", help="Print the URL without opening it")
    return parser


def final_result(status, workspace=None, report=None, warnings=None, error=None):
    summary = audit_summary(report) if report is not None else None
    warnings = list(warnings or [])
    if summary and summary["source_failures"]:
        warnings.append(
            f"{summary['source_failures']} source lookups failed; inspect per-source errors. "
            "Resume preserves these outcomes. Use --refresh (optionally --key) to retry."
        )
    return {
        "schema_version": 1,
        "command": "verify",
        "status": status,
        "complete": status == "completed",
        "output_dir": str(workspace.root) if workspace else None,
        "report_path": str(workspace.final) if workspace and workspace.final.exists() else None,
        "checkpoint_path": str(workspace.checkpoint)
        if workspace and workspace.checkpoint.exists()
        else None,
        "scope": validate_report(report)["mode"] if report is not None else None,
        "summary": summary,
        "warnings": warnings,
        "error": error,
    }


def emit(result, machine):
    for warning in result["warnings"]:
        print(warning, file=sys.stderr)
    if machine:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"Verification: {result['status']}; scope: {result['scope'] or 'unknown'}")
        if result["summary"] is not None:
            print(
                "; ".join(
                    f"{key.replace('_', ' ')}: {value if value is not None else 'unknown'}"
                    for key, value in result["summary"].items()
                )
            )
        if result["output_dir"]:
            print(f"output directory: {result['output_dir']}")
        for field in ("report_path", "checkpoint_path"):
            if result[field]:
                print(f"{field.replace('_', ' ')}: {result[field]}")


def safe_message(exc):
    message = str(exc)
    for key in ("OPENALEX_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"):
        if os.environ.get(key):
            message = message.replace(os.environ[key], "[redacted]")
    return message


def main(argv=None, *, prog="bib-lint"):
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = "--json" in argv
    workspace = report = None
    warnings = []
    try:
        if argv and argv[0] == "parse":
            raise ArgumentError(
                "parse was retired; use bib-lint verify INPUT --output DIRECTORY "
                "or the Python parse_bib API for a parsing-only preview"
            )
        args = arguments(prog).parse_args(argv)
        if args.command == "view":
            from bib_lint.viewer.server import serve

            if not 1 <= args.port <= 65535:
                raise ArgumentError("--port must be between 1 and 65535")
            serve(args.path or "", args.port, no_browser=args.no_browser)
            return 0
        workspace = Workspace.for_input(args.path, args.output)
        workspace, report, warnings = run_audit(
            args.path,
            output=args.output,
            aux=args.aux,
            encoding=args.encoding,
            include_source=args.include_source,
            citation_key=args.key,
            refresh=args.refresh,
            verbose=args.verbose,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
        result = final_result(
            "completed" if report["verification_run"]["complete"] else "partial",
            workspace,
            report,
            warnings,
        )
        emit(result, machine)
        return 0
    except (KeyboardInterrupt, OSError, ValueError, LookupError) as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        # Load only an actual owned artifact; a malformed checkpoint remains an error.
        if workspace is not None and workspace.active().exists():
            try:
                report = json.loads(workspace.active().read_text(encoding="utf-8"))
                validate_report(report)
                warnings = report.get("audit_warnings", [])
            except (OSError, ValueError, TypeError):
                report = None
        message = (
            "Interrupted; rerun the same command to resume saved outcomes."
            if interrupted
            else safe_message(exc)
        )
        print(f"Error: {message}", file=sys.stderr)
        if "args" not in locals() or args.command != "view":
            code = (
                "interrupted"
                if interrupted
                else "arguments"
                if isinstance(exc, ArgumentError)
                else "audit_failed"
            )
            emit(
                final_result(
                    "interrupted" if interrupted else "failed",
                    workspace,
                    report,
                    warnings,
                    {"code": code, "message": message},
                ),
                machine,
            )
        return 130 if interrupted else 2
