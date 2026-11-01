"""Command-line interface for manuscript builds and checks."""

import argparse
import subprocess
from pathlib import Path

import yaml

from sciskill.latex.runner import Project, clean


def main(command, argv=None):
    parser = argparse.ArgumentParser(prog=f"sciskill {command}")
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Project directory"
    )
    parser.add_argument(
        "--main", help="Main LaTeX file (default: manifest latex path or main.tex)"
    )
    if command == "latex-diff":
        parser.add_argument("--base", default="origin/main", help="Target Git revision")
        parser.add_argument("--head", default="HEAD", help="Proposed Git revision")
    if command == "latex-spell":
        parser.add_argument(
            "sources",
            nargs="*",
            help="Source files (default: content/**/*.tex or main file)",
        )
    args = parser.parse_args(argv)
    try:
        project = Project.load(
            args.root, args.main, require_source=command != "latex-clean"
        )
        if command == "latex-build":
            project.build()
            print(f"Built {project.root / '.out' / project.main.with_suffix('.pdf')}")
        elif command == "latex-clean":
            clean(project.root)
        elif command == "latex-lint":
            project.lint()
        elif command == "latex-spell":
            from sciskill.latex.spelling import spell

            return spell(project, args.sources)
        else:
            from sciskill.latex.diff import generate_diff

            generate_diff(project, args.base, args.head)
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout)
        if error.stderr:
            print(error.stderr)
        parser.exit(2, f"{command}: tool exited with status {error.returncode}\n")
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(2, f"{command}: {error}\n")
    return 0
