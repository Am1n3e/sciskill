"""Run the pinned test compiler offline and require complete bibliography output."""

import hashlib
import json
import os
import re
import shlex
import subprocess
from collections import Counter
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_outputs(project: Path, keys: list[str]) -> dict:
    pdf = project / "main.pdf"
    if not pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Compiler did not produce a PDF")
    log = (project / "main.log").read_text(errors="replace")
    if re.search(r"(?:Citation|Reference).*undefined|undefined (?:citations|references)", log):
        raise ValueError("Unresolved citations or references in final LaTeX pass")
    bbl = (project / "main.bbl").read_text(errors="replace")
    rendered = re.findall(r"\\bibitem(?:\[[\s\S]*?\])?\s*\{([^}]+)\}", bbl)
    if Counter(rendered) != Counter(keys):
        raise ValueError(f"Unexpected bibliography occurrence inventory: {rendered}")
    blg = (project / "main.blg").read_text(errors="replace")
    return {
        "rendered_keys": rendered,
        "warnings": [line for line in blg.splitlines() if "Warning--" in line],
        "pdf_sha256": _sha(pdf),
        "output_hashes": {
            name: _sha(project / name) for name in ("main.pdf", "main.bbl", "main.log", "main.blg")
        },
    }


def _docker_command(project: Path, toolchain: dict) -> list[str]:
    passes = [
        f"{shlex.join(command)} > pass-{index}.log 2>&1"
        for index, command in enumerate(toolchain["commands"], 1)
    ]
    script = "\n".join(
        [
            "set -e",
            "pdflatex --version > toolchain.txt",
            "bibtex --version >> toolchain.txt",
            'sha256sum "$(kpsewhich plainnat.bst)" "$(kpsewhich apalike.bst)" >> toolchain.txt',
            *passes,
        ]
    )
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--platform",
        toolchain["platform"],
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--env",
        "SOURCE_DATE_EPOCH=946684800",
        "--env",
        "FORCE_SOURCE_DATE=1",
        "--env",
        "TZ=UTC",
        "--mount",
        f"type=bind,src={project.resolve()},dst=/work",
        "--workdir",
        "/work",
        toolchain["image"],
        "sh",
        "-c",
        script,
    ]


def _cached(project: Path, fingerprint: str) -> dict | None:
    receipt = project / "build.json"
    if not receipt.exists():
        return None
    saved = json.loads(receipt.read_text())
    if saved.get("fingerprint") != fingerprint:
        return None
    hashes = saved.get("output_hashes", {})
    if not hashes or any(
        not (project / p).is_file() or _sha(project / p) != sha for p, sha in hashes.items()
    ):
        return None
    return saved


def compile_project(project: Path) -> dict:
    recipe_path = project / "recipe.json"
    recipe = json.loads(recipe_path.read_text())
    for name, expected in recipe["files"].items():
        if _sha(project / name) != expected:
            raise ValueError(f"Changed build input: {name}")
    fingerprint = hashlib.sha256(recipe_path.read_bytes() + Path(__file__).read_bytes()).hexdigest()
    if cached := _cached(project, fingerprint):
        return cached
    for suffix in ("aux", "bbl", "blg", "log", "pdf", "out", "brf"):
        (project / f"main.{suffix}").unlink(missing_ok=True)
    (project / "build.json").unlink(missing_ok=True)
    result = subprocess.run(
        _docker_command(project, recipe["toolchain"]), capture_output=True, text=True, timeout=240
    )
    (project / "container.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError(f"Compiler exited {result.returncode}; see pass logs in {project}")
    receipt = inspect_outputs(project, list(recipe["key_map"].values()))
    receipt.update(
        {
            "fingerprint": fingerprint,
            "status": "compiled",
            "project": str(project),
            "toolchain": (project / "toolchain.txt").read_text(),
            "commands": recipe["toolchain"]["commands"],
        }
    )
    (project / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
