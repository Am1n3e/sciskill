"""Build a rendered manuscript diff from two committed Git revisions."""

import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from sciskill.latex.runner import Project


def _git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root)


def comparison_revisions(root, base, head):
    """Compare the PR head with its merge base, matching GitHub Files changed."""
    base_sha, head_sha = [
        _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        .decode()
        .strip()
        for ref in (base, head)
    ]
    merge_base = _git(root, "merge-base", base_sha, head_sha).decode().strip()
    return merge_base, head_sha


def export_revision(root, revision, destination):
    """Export tracked regular files without following archive symlinks."""
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(_git(root, "archive", revision))) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not (member.isdir() or member.isfile())
            ):
                raise ValueError(f"Unsupported archive entry: {member.name}")
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def generate_diff(project, base, head):
    """Flatten included sections and generated bibliographies, then compile."""
    root = Path(
        _git(project.root, "rev-parse", "--show-toplevel").decode().strip()
    ).resolve()
    relative = project.root.relative_to(root)
    base_sha, head_sha = comparison_revisions(root, base, head)
    output = project.prepare_output()
    for name in ("paper-diff.pdf", "paper.pdf"):
        (output / name).unlink(missing_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="paper-diff-", dir=output))
    old, new = scratch / "base", scratch / "head"
    print(f"Comparing {base_sha[:12]} → {head_sha[:12]}")
    for revision, snapshot in ((base_sha, old), (head_sha, new)):
        export_revision(root, revision, snapshot)
        paper = Project.load(snapshot / relative, str(project.main))
        paper.build()
        # latexdiff --flatten expands bibliography only when main.bbl is beside main.tex.
        # https://github.com/ftilmann/latexdiff/blob/master/latexdiff
        bbl = paper.root / ".out" / paper.main.with_suffix(".bbl")
        if bbl.exists():
            shutil.copyfile(bbl, paper.root / paper.main.with_suffix(".bbl"))
    main = relative / project.main
    difference = Project(scratch, project.main).run(
        "latexdiff",
        "--flatten",
        f"base/{main.as_posix()}",
        f"head/{main.as_posix()}",
        capture=True,
    )
    paper = Project.load(new / relative, str(project.main))
    diff_name = "sciskill-diff.tex"
    if paper.main.name == diff_name:
        raise ValueError("The main manuscript cannot be named sciskill-diff.tex")
    (paper.root / diff_name).write_text(difference.stdout, encoding="utf-8")
    paper.build(diff_name)
    shutil.copyfile(paper.root / ".out/sciskill-diff.pdf", output / "paper-diff.pdf")
    shutil.copyfile(
        paper.root / ".out" / paper.main.with_suffix(".pdf"), output / "paper.pdf"
    )
    shutil.rmtree(scratch)
    print("Built .out/paper-diff.pdf and .out/paper.pdf")
