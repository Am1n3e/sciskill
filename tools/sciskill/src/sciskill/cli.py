"""Dispatch standalone tools through a single public command."""

import argparse
from importlib.metadata import version


def main():
    parser = argparse.ArgumentParser(
        prog="sciskill", description="Agent tools and skills for scientists."
    )
    parser.add_argument(
        "--version", action="version", version=f"sciskill {version('sciskill')}"
    )
    parser.add_argument("tool", choices=["bib-lint", "rebuttal"], help="Tool to run")
    parser.add_argument(
        "arguments", nargs=argparse.REMAINDER, help="Tool action and options"
    )
    args = parser.parse_args()
    if args.tool == "bib-lint":
        from bib_lint.cli import main as run

        return run(args.arguments, prog="sciskill bib-lint")
    from rebuttal_desk.cli import main as run

    return run(args.arguments, prog="sciskill rebuttal")
