"""Generate native-style papers without reading any expected audit answers."""

import hashlib
import json
import re
from pathlib import Path

from bib_lint.parser import parse_file

BODY = Path(__file__).with_name("paper_body.tex")
TITLE = "Planning and Evaluation for Language Model Agents"
EXTRAS = {
    "neurips": r"\usepackage[T1]{fontenc}\usepackage{hyperref}\usepackage{url}",
    "icml": r"\usepackage{microtype}\usepackage{graphicx}\usepackage{hyperref}",
    "iclr": r"\usepackage{times}\usepackage{hyperref}\usepackage{url}",
    "aaai": r"""\usepackage{times}\usepackage{helvet}\usepackage{courier}
\usepackage[hyphens]{url}\usepackage{graphicx}\usepackage{natbib}\usepackage{caption}
\urlstyle{rm}\def\UrlFont{\rm}\frenchspacing
\setlength{\pdfpagewidth}{8.5in}\setlength{\pdfpageheight}{11in}
\setcounter{secnumdepth}{0}\affiliations{Anonymous Institution}""",
    "ijcai": r"""\pdfpagewidth=8.5in\pdfpageheight=11in
\usepackage{times}\usepackage{url}\usepackage[hidelinks]{hyperref}
\usepackage[switch]{lineno}\linenumbers\urlstyle{same}
\pdfinfo{/TemplateVersion (IJCAI.2027.0)}""",
    "aistats": r"\usepackage[round]{natbib}\usepackage{url}",
    "acl": r"""\usepackage{times}\usepackage{latexsym}\usepackage[T1]{fontenc}
\usepackage{microtype}\usepackage{inconsolata}\usepackage{graphicx}""",
    "cvpr": r"""\input{preamble}
\definecolor{cvprblue}{rgb}{0.21,0.49,0.74}
\usepackage[pagebackref,breaklinks,colorlinks,allcolors=cvprblue]{hyperref}""",
    "eccv": r"""\usepackage{eccvabbrv}\usepackage{graphicx}\usepackage{booktabs}
\usepackage[accsupp]{axessibility}\usepackage{hyperref}\usepackage{orcidlink}""",
}


def build_bibliography(source: Path, *, selected_keys: list[str] | None = None) -> tuple[str, dict]:
    """Substitute only entry headers, retaining fields, names, comments, and ordering."""
    original = parse_file(source)
    selected = list(original.entries) if selected_keys is None else selected_keys
    if len(set(selected)) != len(selected) or any(key not in original.entries for key in selected):
        raise ValueError("Invalid bibliography selection")
    key_map = {
        key: f"ref{index:04d}" for index, key in enumerate(original.entries, 1) if key in selected
    }
    source_text = original.source_text
    if selected_keys is not None:
        headers = list(re.finditer(r"(?m)^@[A-Za-z]+\s*\{\s*([^,}\s]+)", source_text))
        if {match[1] for match in headers} != set(original.entries):
            raise ValueError("Cannot safely isolate this bibliography selection")
        source_text = "\n".join(
            source_text[
                match.start() : headers[index + 1].start()
                if index + 1 < len(headers)
                else len(source_text)
            ]
            for index, match in enumerate(headers)
            if match[1] in selected
        )
    pattern = re.compile(r"(@[A-Za-z]+\s*\{\s*)([^,}\s]+)(\s*[,}])")
    text = pattern.sub(
        lambda match: match[1] + key_map.get(match[2], match[2]) + match[3],
        source_text,
    )
    return text, key_map


def _command(command: str, spec: dict) -> str:
    options = ",".join(spec["options"])
    return "\\" + command + (f"[{options}]" if options else "") + "{" + spec["name"] + "}"


def _opening(family: str) -> str:
    if family == "icml":
        return rf"""\icmltitlerunning{{{TITLE}}}
\begin{{document}}\twocolumn[\icmltitle{{{TITLE}}}
\begin{{icmlauthorlist}}\icmlauthor{{Anonymous Author}}{{anon}}\end{{icmlauthorlist}}
\icmlaffiliation{{anon}}{{Anonymous Institution}}
\icmlcorrespondingauthor{{Anonymous Author}}{{anonymous@example.org}}\vskip 0.3in]
\printAffiliationsAndNotice{{}}"""
    if family == "aistats":
        return rf"""\begin{{document}}\twocolumn[\aistatstitle{{{TITLE}}}
\aistatsauthor{{Anonymous Author}}\aistatsaddress{{Anonymous Institution}}]"""
    extra = r"\institute{Anonymous Institution}" if family == "eccv" else ""
    return (
        rf"\title{{{TITLE}}}\author{{Anonymous Author}}"
        + extra
        + "\n"
        + (r"\begin{document}\maketitle")
    )


def paper_source(venue: dict, keys: list[str]) -> str:
    preamble = [
        _command("documentclass", venue["document_class"]),
        r"\usepackage[utf8]{inputenc}",
        _command("usepackage", venue["style_package"]),
        EXTRAS[venue["family"]],
    ]
    preamble.extend(rf"\def\{name}{{{value}}}" for name, value in venue["macros"].items())
    if venue["family"] == "iclr" and venue["mode"] == "final":
        preamble.append(r"\iclrfinalcopy")
    citations = " ".join(
        r"\cite{" + ",".join(keys[i : i + 4]) + "}." for i in range(0, len(keys), 4)
    )
    body = BODY.read_text(encoding="utf-8").replace("CITATIONS", citations)
    bibliography = venue["bibliography"]
    style = (
        ""
        if bibliography["selected_by_style"]
        else (r"\bibliographystyle{" + bibliography["style"] + "}")
    )
    references = style + "\n" + r"\bibliography{references}"
    if venue["family"] == "cvpr":
        references = "{\\small\n" + references + "\n}"
    ending = references + "\n" + r"\end{document}"
    return "\n".join([*preamble, _opening(venue["family"]), body, ending]) + "\n"


def create_project(
    venue: dict,
    corpus: dict,
    asset_dir: Path,
    fixtures: Path,
    output: Path,
    *,
    selected_keys: list[str] | None = None,
    variant: str = "baseline",
) -> Path:
    text, key_map = build_bibliography(
        fixtures / "corpora" / corpus["path"], selected_keys=selected_keys
    )
    files = {
        str(path.relative_to(asset_dir)): path.read_bytes()
        for path in asset_dir.rglob("*")
        if path.is_file()
    }
    files["main.tex"] = paper_source(venue, list(key_map.values())).encode()
    files["references.bib"] = text.encode()
    templates = json.loads((fixtures / "templates.json").read_text())
    recipe = {
        "venue": venue,
        "corpus": corpus,
        "toolchain": templates["toolchain"],
        "asset": templates["assets"][venue["asset"]],
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())},
        "key_map": key_map,
        "selection": {
            "variant": variant,
            "included": list(key_map),
            "excluded": [key for key in corpus["entry_keys"] if key not in key_map],
        },
    }
    build_id = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
    project = output / venue["id"] / corpus["id"] / build_id
    project.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (project / "recipe.json").write_text(json.dumps(recipe, indent=2) + "\n")
    return project
