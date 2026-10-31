"""Account for original build negatives and explicitly named renderable subsets."""

import json
from pathlib import Path

from pdf_e2e.compiler import compile_project
from pdf_e2e.projects import create_project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/pdf"


def excluded_cases(venue: dict, corpus: str) -> dict:
    rules = json.loads((FIXTURES / "build_cases.json").read_text())
    return {
        **rules["shared_negatives"].get(corpus, {}),
        **rules["family_negatives"].get(venue["family"], {}).get(corpus, {}),
    }


def expected_failure(project: Path, negatives: dict) -> bool:
    logs = "\n".join(path.read_text(errors="replace") for path in project.glob("pass-*.log"))
    return any(case["diagnostic"] in logs for case in negatives.values())


def compile_renderable(venue, corpus, asset_dir, fixtures, output):
    excluded = excluded_cases(venue, corpus["id"])
    keys = [key for key in corpus["entry_keys"] if key not in excluded]
    project = create_project(
        venue,
        corpus,
        asset_dir,
        fixtures,
        output,
        selected_keys=keys if excluded else None,
        variant="renderable-subset" if excluded else "baseline",
    )
    receipt = compile_project(project)
    return {
        "venue": venue["id"],
        "corpus": corpus["id"],
        "status": "compiled",
        "project": str(project),
        "excluded": excluded,
        "pdf_sha256": receipt["pdf_sha256"],
    }


def compile_negative(venue, corpus, key, case, asset_dir, fixtures, output):
    project = create_project(
        venue,
        corpus,
        asset_dir,
        fixtures,
        output,
        selected_keys=[key, *case.get("with", [])],
        variant="isolated-build-negative",
    )
    try:
        compile_project(project)
    except ValueError:
        if expected_failure(project, {key: case}):
            return {
                "venue": venue["id"],
                "corpus": corpus["id"],
                "key": key,
                "status": "expected_build_failure",
                "project": str(project),
                **case,
            }
        raise
    raise ValueError(f"Expected build-negative unexpectedly compiled: {venue['id']}/{key}")


def complete_matrix(baseline: dict, templates: dict, corpora: list, cache: Path, output: Path):
    """Keep original outcomes; add reviewed failures and PDFs for every renderable case."""
    import subprocess
    import sys

    renderable, negatives, counterparts, errors = [], [], [], []
    accepted = 0
    for cell in baseline["builds"]:
        venue = next(v for v in templates["venues"] if v["id"] == cell["venue"])
        corpus = next(c for c in corpora if c["id"] == cell["corpus"])
        excluded = excluded_cases(venue, corpus["id"])
        asset_dir = cache / templates["assets"][venue["asset"]]["sha256"]
        expected = cell["status"] == "compiled" or (
            cell.get("project") and expected_failure(Path(cell["project"]), excluded)
        )
        cell["expected_failure_confirmed"] = cell["status"] == "failed" and bool(expected)
        accepted += bool(expected)
        try:
            rendered = compile_renderable(venue, corpus, asset_dir, FIXTURES, output)
            renderable.append(rendered)
            for key, case in excluded.items():
                negatives.append(
                    compile_negative(venue, corpus, key, case, asset_dir, FIXTURES, output)
                )
                if case.get("renderable_alone"):
                    path = create_project(
                        venue,
                        corpus,
                        asset_dir,
                        FIXTURES,
                        output,
                        selected_keys=[key],
                        variant="isolated-renderable-counterpart",
                    )
                    receipt = compile_project(path)
                    counterparts.append(
                        {
                            "venue": venue["id"],
                            "corpus": corpus["id"],
                            "status": "compiled",
                            "project": str(path),
                            "key": key,
                            "pdf_sha256": receipt["pdf_sha256"],
                        }
                    )
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            errors.append({"venue": venue["id"], "corpus": corpus["id"], "error": str(error)})
        print(f"acceptance {venue['id']}/{corpus['id']}: checked", file=sys.stderr, flush=True)
    baseline.update(
        accepted_original_builds=accepted,
        renderable_builds=renderable,
        isolated_build_negatives=negatives,
        renderable_counterparts=counterparts,
        build_diagnostics=errors,
    )
    baseline["complete"] = (
        not errors
        and accepted == baseline["required_builds"]
        and len(renderable) == baseline["required_builds"]
        and all(cell["status"] == "compiled" for cell in renderable)
        and len(negatives)
        == sum(len(excluded_cases(v, c["id"])) for v in templates["venues"] for c in corpora)
    )
    (output / "acceptance.json").write_text(json.dumps(baseline, indent=2) + "\n")
    return baseline
