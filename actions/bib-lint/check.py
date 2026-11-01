"""Run a read-only PR bibliography audit and write a GitHub check summary."""

import contextlib
import html
import json
import os
from pathlib import Path


def render(result, report):
    from bib_lint.status import reference_status

    heading = "## New reference check\n\n"
    if not result.get("complete") or report is None:
        message = (result.get("error") or {}).get("message", "Inspect the audit diagnostics.")
        return heading + "Audit could not complete. " + html.escape(message) + "\n"
    if result["summary"]["eligible"] == 0:
        return heading + "No new references. No source lookups were needed.\n"
    rows = []
    for item in report["items"]:
        status = reference_status(item["validations"])
        label = (
            "Valid" if status == "Correct" else "Invalid" if status == "Invalid" else "Unresolved"
        )
        key = html.escape(item["entry"]["key"])
        rows.append(f"<tr><td><code>{key}</code></td><td>{label}</td></tr>")
    return (
        heading
        + "Only citation keys added by this PR were checked.\n\n"
        + "<table><thead><tr><th>Reference</th><th>Result</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>\n\n"
        + "Confirmed invalid references fail this check. Unresolved references need review; "
        + "a missing source response does not prove a citation is invalid. "
        + "Download the audit artifact for per-source evidence.\n"
    )


def main():
    from bib_lint.cli import main as verify

    output = Path(os.environ["SCISKILL_BIB_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "result.json"
    arguments = [
        "verify",
        os.environ["SCISKILL_BIB_PATH"],
        "--base",
        os.environ["SCISKILL_BIB_BASE"],
        "--head",
        os.environ["SCISKILL_BIB_HEAD"],
        "--output",
        str(output / "audit"),
        "--json",
        "--fail-on-invalid",
    ]
    with result_path.open("w", encoding="utf-8") as stream, contextlib.redirect_stdout(stream):
        code = verify(arguments)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report_path = result.get("report_path") or result.get("checkpoint_path")
    report = json.loads(Path(report_path).read_text(encoding="utf-8")) if report_path else None
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
        stream.write(render(result, report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
