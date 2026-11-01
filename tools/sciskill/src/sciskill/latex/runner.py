"""Run the pinned TeX toolchain with read-only manuscript inputs."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

TEX_IMAGE = (
    "ghcr.io/xu-cheng/texlive-alpine@"
    "sha256:0768bec1654eb3692aace2faca186d190f86d5f510ae20d71a5145d67aff081c"
)
DATA = Path(__file__).parent / "data"


def output_directory(root):
    output = root / ".out"
    if output.is_symlink():
        raise ValueError("Build output .out must not be a symlink")
    if output.exists() and not output.is_dir():
        raise ValueError("Build output .out must be a directory")
    return output


def clean(root):
    output = output_directory(Path(root).resolve())
    if output.exists():
        shutil.rmtree(output)


@dataclass(frozen=True)
class Project:
    root: Path
    main: Path

    @classmethod
    def load(cls, root, main=None, *, require_source=True):
        root = Path(root).resolve()
        if main is None:
            config = root / ".sciskill/config.yaml"
            if config.exists():
                data = yaml.safe_load(config.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("version") != 1:
                    raise ValueError(
                        "SciSkill configuration must be a version 1 mapping"
                    )
                main = data.get("latex")
                if main is not None and not isinstance(main, str):
                    raise ValueError("The latex setting must be a source path")
        path = (root / (main or "main.tex")).resolve()
        if not path.is_relative_to(root):
            raise ValueError("LaTeX source must be inside the project root")
        if path.is_dir():
            root, path = path, path / "main.tex"
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError("LaTeX source must be inside the project root")
        # Compile from the main file's directory so relative includes work.
        if require_source and (not path.is_file() or path.suffix != ".tex"):
            raise ValueError(f"LaTeX source file not found: {path}")
        return cls(path.parent, Path(path.name))

    def prepare_output(self):
        output = output_directory(self.root)
        output.mkdir(exist_ok=True)
        return output

    def config(self, name):
        return f"./{name}" if (self.root / name).is_file() else f"/sciskill/{name}"

    def run(self, *arguments, capture=False, check=True):
        output = self.prepare_output()
        command = [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--network",
            "none",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            "HOME=/tmp",
            "--mount",
            f"type=bind,src={self.root},dst=/paper,readonly",
            "--mount",
            f"type=bind,src={output},dst=/paper/.out",
            "--mount",
            f"type=bind,src={DATA.resolve()},dst=/sciskill,readonly",
            "--workdir",
            "/paper",
            TEX_IMAGE,
            *map(str, arguments),
        ]
        return subprocess.run(command, text=True, capture_output=capture, check=check)

    def build(self, filename=None):
        return self.run(
            "latexmk",
            "-norc",
            "-r",
            self.config(".latexmkrc"),
            "-outdir=.out",
            "-auxdir=.out",
            f"./{filename or self.main}",
        )

    def lint(self):
        return self.run("chktex", "-l", self.config(".chktexrc"), f"./{self.main}")
