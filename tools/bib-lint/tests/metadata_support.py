"""Small fixed records and mutations used by focused metadata regressions."""

import html
from dataclasses import asdict

from bib_lint.parser import parse_string
from bib_lint.verification.matching import name_parts

_PAPERS = {
    "codenav": (
        "CodeNav: Beyond tool-use to using real-world codebases with LLM agents",
        "Tanmay Gupta|Luca Weihs|Aniruddha Kembhavi",
        "2024",
        "arXiv",
        "https://arxiv.org/abs/2406.12276v1",
        {"arxiv": "2406.12276v1"},
        "preprint",
        "published",
    ),
    "datawise": (
        "DatawiseAgent: A Notebook-Centric LLM Agent Framework "
        "for Adaptive and Robust Data Science Automation",
        "Ziming You|Yumiao Zhang|Dexuan Xu|Yiwei Lou|Yandong Yan|Wei Wang|Huamin Zhang|Yu Huang",
        "2025",
        "Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing",
        "https://aclanthology.org/2025.emnlp-main.58/",
        {"acl": "2025.emnlp-main.58", "doi": "10.18653/v1/2025.emnlp-main.58"},
        "publication",
        "published",
    ),
    "sb3": (
        "Stable-Baselines3: Reliable Reinforcement Learning Implementations",
        "Antonin Raffin|Ashley Hill|Adam Gleave|Anssi Kanervisto|Maximilian Ernestus|Noah Dormann",
        "2021",
        "Journal of Machine Learning Research",
        "https://jmlr.org/papers/v22/20-1364.html",
        {"jmlr": "v22/20-1364"},
        "publication",
        "published",
    ),
    "hcpi": (
        "High Confidence Policy Improvement",
        "Philip Thomas|Georgios Theocharous|Mohammad Ghavamzadeh",
        "2015",
        "International Conference on Machine Learning",
        "https://proceedings.mlr.press/v37/thomas15.html",
        {"pmlr": "v37/thomas15"},
        "publication",
        "published",
    ),
    "pal_accepted": (
        "PAL: Program-aided Language Models",
        "Luyu Gao|Aman Madaan|Shuyan Zhou|Uri Alon|Pengfei Liu|Yiming Yang|"
        "Jamie Callan|Graham Neubig",
        "2023",
        "ICML 2023 Poster",
        "https://openreview.net/forum?id=M1fd9Z00sj",
        {"openreview": "M1fd9Z00sj"},
        "publication",
        "accepted",
    ),
    "gaia": (
        "GAIA: a benchmark for General AI Assistants",
        "Grégoire Mialon|Clémentine Fourrier|Craig Swift|Thomas Wolf|Yann LeCun|Thomas Scialom",
        "2023",
        "arXiv",
        "https://arxiv.org/abs/2311.12983v1",
        {"arxiv": "2311.12983v1"},
        "preprint",
        "published",
    ),
}


def _record(paper):
    title, names, year, venue, url, identifiers, kind, status = paper
    return {
        "title": title,
        "authors": [name_parts(n) for n in names.split("|")],
        "year": year,
        "venue": venue,
        "url": url,
        "identifiers": identifiers,
        "record_type": kind,
        "publication_status": status,
        "provenance": {"source": url},
    }


RECORDS = {name: {"record": _record(paper)} for name, paper in _PAPERS.items()}
_CASES = {
    "adv_match_family_boundary_collision": (
        "codenav",
        {"author": "Tanmay Gupta, and Weihs, Luca and Kembhavi, Aniruddha"},
    ),
    "adv_match_literal_prefix_collision": ("codenav", {"author": "{Tanmay Gupta} and others"}),
    "adv_match_arxiv_concatenated_identifiers": (
        "codenav",
        {"eprint": "2406.12276v1/2411.15124v5"},
    ),
    "adv_match_arxiv_double_version": ("codenav", {"eprint": "2406.12276v1v5"}),
    "adv_match_arxiv_foreign_url_identifier": (
        "codenav",
        {"eprint": "https://evil.example/2406.12276v1"},
    ),
    "adv_match_doi_tex_escaped_percent": (
        "datawise",
        {"doi": r"HTTPS://doi.org/10.18653\%2Fv1\%2F2025.EMNLP-MAIN.58"},
    ),
    "adv_match_title_tex_emphasis": (
        "codenav",
        {"title": r"\emph{CodeNav}: Beyond tool-use to using real-world codebases with LLM agents"},
    ),
    "adv_consensus_arxiv_impostor_venue": (
        "codenav",
        {"journal": "Proceedings of the arXiv Research Society"},
    ),
    "adv_match_clean_unicode_decomposed": ("gaia", {}),
    "adv_provider_split_arxiv_url": ("codenav", {"url": "https://arxiv.org/abs/2411.15124v5"}),
    "adv_provider_shadowed_version_pin": (
        "codenav",
        {"eprint": "2406.12276", "url": "https://arxiv.org/abs/2406.12276v999"},
    ),
    "adv_provider_shadowed_journal_id": (
        "codenav",
        {"journal": "arXiv preprint arXiv:2411.15124v5"},
    ),
    "adv_provider_acl_alias_conflict": ("datawise", {"acl_id": "2024.acl-long.505"}),
    "adv_provider_openreview_alias_conflict": ("pal_accepted", {"openreview_id": "unrelated-note"}),
    "adv_provider_duplicate_forum_id": (
        "pal_accepted",
        {"url": "https://openreview.net/forum?id=M1fd9Z00sj&id=unrelated-note"},
    ),
    "adv_provider_pmlr_alias_conflict": ("hcpi", {"pmlr_id": "v70/shi17a"}),
    "adv_consensus_shadowed_booktitle": (
        "datawise",
        {
            "journal": _PAPERS["datawise"][3],
            "booktitle": "Advances in Neural Information Processing Systems",
        },
    ),
    "adv_consensus_datawise_primary_control": ("datawise", {}),
    "adv_flow_CodeNav/../%2E%2E": ("codenav", {}),
    "JMLR:v22:20-1364": ("sb3", {}),
}


def bibtex(key):
    base, changed = _CASES[key]
    record = RECORDS[base]["record"]
    fields = {
        "title": record["title"],
        "year": record["year"],
        "url": record["url"],
        "author": " and ".join(f"{a['family']}, {a['given']}" for a in record["authors"]),
    }
    if record["record_type"] == "preprint":
        fields.update(eprint=record["identifiers"]["arxiv"], archiveprefix="arXiv")
    else:
        fields["journal" if base == "sb3" else "booktitle"] = record["venue"]
    if "doi" in record["identifiers"]:
        fields["doi"] = record["identifiers"]["doi"]
    if base == "sb3":
        fields["volume"] = "22"
    fields.update(changed)
    kind = (
        "misc"
        if record["record_type"] == "preprint"
        else "article"
        if base == "sb3"
        else "inproceedings"
    )
    return (
        "@"
        + kind
        + "{"
        + key
        + ",\n"
        + ",\n".join("  " + name + "={" + value + "}" for name, value in fields.items())
        + "\n}\n"
    )


def entry(key):
    return asdict(parse_string(bibtex(key)).entries[key])


def write_bib(path, key):
    path.write_text(bibtex(key))
    return path


def html_record(base):
    """Fixed response facts remain independent of any input mutation."""
    record = RECORDS[base]["record"]
    values = [
        ("citation_title", record["title"]),
        ("citation_publication_date", record["year"]),
        ("citation_journal_title", record["venue"]),
    ]
    values.extend(("citation_author", name) for name in _PAPERS[base][1].split("|"))
    if "doi" in record["identifiers"]:
        values.append(("citation_doi", record["identifiers"]["doi"]))
    return (
        "<html><head>"
        + "".join(
            f'<meta name="{name}" content="{html.escape(value, quote=True)}">'
            for name, value in values
        )
        + "</head></html>"
    )


def atom_record(base):
    record = RECORDS[base]["record"]
    return '<feed xmlns="http://www.w3.org/2005/Atom"><entry>' + (
        "<id>"
        + html.escape(record["url"])
        + "</id><title>"
        + html.escape(record["title"])
        + "</title><published>"
        + record["year"]
        + "-01-01T00:00:00Z</published>"
        + "".join(
            "<author><name>" + html.escape(name) + "</name></author>"
            for name in _PAPERS[base][1].split("|")
        )
        + "</entry></feed>"
    )
