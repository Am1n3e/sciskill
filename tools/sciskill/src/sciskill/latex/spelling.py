"""Select spelling diagnostics from the pinned TeXtidote plain report."""

import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen

VERSION = "0.9"
URL = f"https://github.com/sylvainhalle/textidote/releases/download/v{VERSION}/textidote.jar"
SHA256 = "3ad1aaa0922709f8c9dc0cdc9d476f475c00c3368de6c1492f0004c0a3418de7"
SPELLING_RULE = "lt:en:MORFOLOGIK_RULE_EN_US"


def spell(project, sources):
    """Check explicit sections, or included manuscript prose, for spelling only."""
    output = project.prepare_output()
    files = (
        [project.root / source for source in sources]
        if sources
        else sorted(project.root.glob("content/**/*.tex"))
    )
    fragments = bool(files)
    files = files or [project.root / project.main]
    for source in files:
        if not source.resolve().is_relative_to(project.root) or not source.is_file():
            raise ValueError(
                f"Spelling source must be a file inside the project: {source}"
            )
    jar = textidote_jar(output / "tools")
    arguments = []
    # Paper-specific TeXtidote policy takes precedence over the bundled defaults.
    if not (project.root / ".textidote").exists():
        arguments = [
            "--check",
            "en",
            "--output",
            "plain",
            "--no-color",
            "--read-all",
            "--replace",
            "/sciskill/textidote-replacements",
        ]
        if fragments:
            arguments.append("--single-file")
        if (project.root / "spelling.txt").is_file():
            arguments.extend(["--dict", "spelling.txt"])
    result = project.run(
        "java",
        "-jar",
        jar.relative_to(project.root).as_posix(),
        *arguments,
        *(f"./{source.relative_to(project.root).as_posix()}" for source in files),
        capture=True,
        check=False,
    )
    (output / "spell.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    findings = spelling_findings(
        result.stdout,
        result.stderr,
        result.returncode,
        files[0].relative_to(project.root).as_posix(),
    )
    for finding in findings:
        print(finding)
    print(f"Found {len(findings)} spelling issue(s)" if findings else "Spelling passed")
    return 1 if findings else 0


def _checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def textidote_jar(directory):
    """Download the official release once and verify it before every execution."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"textidote-{VERSION}.jar"
    if directory.is_symlink() or target.is_symlink():
        raise ValueError("TeXtidote cache must not be a symlink")
    if not target.exists():
        print(f"Downloading TeXtidote {VERSION}...")
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with urlopen(URL, timeout=60) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            if _checksum(temporary) != SHA256:
                raise ValueError("TeXtidote download failed SHA-256 verification")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    if _checksum(target) != SHA256:
        raise ValueError(
            "Cached TeXtidote failed SHA-256 verification; run uvx sciskill latex-clean"
        )
    return target


def spelling_findings(stdout, stderr, returncode, default_filename="main.tex"):
    """Keep US-English dictionary findings; reject incomplete or failed runs.

    TeXtidote's exit status counts all advice, including grammar. Its plain
    renderer preserves filenames and rule IDs across included files, unlike
    the 0.9 JSON renderer. Report format: https://github.com/sylvainhalle/textidote
    """
    summary = re.search(r"Found (\d+) warning\(s\)", stderr)
    if (
        not summary
        or returncode != int(summary[1]) % 256
        or re.search(
            r"Exception|\bError\b|not found|skipping|Cannot open|Unknown language",
            stderr,
        )
    ):
        raise ValueError(f"TeXtidote failed:\n{stderr.strip()}")

    filename = default_filename
    blocks = []
    for line in stdout.splitlines():
        if line and not line.startswith((" ", "*")) and line.endswith(".tex"):
            filename = line
        elif re.match(r"^\* (?:L\d+C\d+|\?)", line):
            blocks.append((filename, [line]))
        elif blocks and line.startswith("  "):
            blocks[-1][1].append(line.strip())
    if len(blocks) != int(summary[1]) or (
        int(summary[1]) == 0 and "Everything is OK!" not in stdout
    ):
        raise ValueError("Incomplete or unrecognized TeXtidote report")

    findings = []
    for filename, lines in blocks:
        block = " ".join(lines)
        rule = re.search(r"\[((?:lt|sh):[^\]]+)\]", block)
        if not rule:
            raise ValueError("TeXtidote diagnostic has no rule identifier")
        if rule[1] != SPELLING_RULE:
            continue
        location = re.match(r"^\* L(\d+)C(\d+)\S* (.*)", block)
        if not location:
            raise ValueError(f"Cannot locate spelling diagnostic in {filename}")
        message = block[location.start(3) : rule.start()].strip()
        message = re.sub(r"\s+\(\d+\)$", "", message)
        findings.append(f"{filename}:{location[1]}:{location[2]}: {message}")
    return findings
