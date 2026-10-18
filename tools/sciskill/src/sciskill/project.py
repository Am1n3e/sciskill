"""Initialize project-local SciSkill configuration and disposable storage."""

import argparse
import os
import tempfile
from pathlib import Path

import yaml

from sciskill.requirements import check_required_tools

IGNORE_ENTRIES = {".sciskill", ".sciskill/", "/.sciskill", "/.sciskill/"}


def source_path(value, root, *, allow_directory=False):
    path = Path(value).expanduser()
    path = (root / path).resolve()
    if not path.is_file() and not (allow_directory and path.is_dir()):
        raise ValueError(f"Input path does not exist or has the wrong type: {value}")
    return os.path.relpath(path, root)


def write_config(path, config):
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".config-",
        suffix=".yaml",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            yaml.safe_dump(config, stream, sort_keys=False, allow_unicode=True)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize(root, *, latex=None, bib=None, venue=None, update_gitignore=False):
    root = Path(root).resolve()
    directory = root / ".sciskill"
    config_path = directory / "config.yaml"
    for path in (directory, config_path, directory / "cache", directory / "tmp"):
        if path.is_symlink():
            raise ValueError(f"Refusing to initialize through a symlink: {path}")
    if directory.exists() and not directory.is_dir():
        raise ValueError(".sciskill must be a directory")
    for path in (directory / "cache", directory / "tmp"):
        if path.exists() and not path.is_dir():
            raise ValueError(f"{path.name} must be a directory")
    config = {"version": 1, "latex": None, "bib": None, "venue": None}
    if config_path.exists():
        existing = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("version") != 1:
            raise ValueError(
                "Existing SciSkill configuration must be a version 1 mapping"
            )
        config.update(existing)
    if latex is not None:
        config["latex"] = source_path(latex, root, allow_directory=True)
    if bib is not None:
        config["bib"] = source_path(bib, root)
    if venue is not None:
        config["venue"] = venue
    ignore_path = root / ".gitignore"
    ignore_content = None
    if update_gitignore:
        if ignore_path.is_symlink():
            raise ValueError("Refusing to update a symlinked .gitignore")
        ignore_content = ignore_path.read_bytes() if ignore_path.exists() else b""
        entries = {line.strip() for line in ignore_content.decode("utf-8").splitlines()}
        if entries & IGNORE_ENTRIES:
            ignore_content = None
        else:
            separator = (
                b"" if not ignore_content or ignore_content.endswith(b"\n") else b"\n"
            )
            ignore_content += separator + b".sciskill/\n"
    directory.mkdir(exist_ok=True)
    (directory / "cache").mkdir(exist_ok=True)
    (directory / "tmp").mkdir(exist_ok=True)
    write_config(config_path, config)
    if ignore_content is not None:
        ignore_path.write_bytes(ignore_content)
    return config_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="sciskill init", description="Initialize the current project."
    )
    parser.add_argument("--latex", help="LaTeX source file or directory")
    parser.add_argument("--bib", help="Bibliography file")
    parser.add_argument("--venue", help="Target publication venue (optional)")
    parser.add_argument(
        "--update-gitignore",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Ignore .sciskill/ in .gitignore (default: off)",
    )
    args = parser.parse_args(argv)
    try:
        versions = check_required_tools()
        path = initialize(
            Path.cwd(),
            latex=args.latex,
            bib=args.bib,
            venue=args.venue,
            update_gitignore=args.update_gitignore,
        )
    except (ValueError, OSError, yaml.YAMLError) as exc:
        parser.exit(2, f"sciskill init: {exc}\n")
    print("Required tools ready: " + ", ".join(versions.values()))
    print(f"Initialized {path}")
    return 0
