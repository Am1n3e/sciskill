"""Held-out native paper modes exercise layouts beyond the review baseline."""

from pdf_e2e.build import FIXTURES, read_json
from pdf_e2e.projects import paper_source


def test_stress_modes_are_distinct_native_configurations():
    from pdf_e2e.matrix import stress_definitions

    original = read_json(FIXTURES / "templates.json")
    configurations = stress_definitions(original)
    assert [(venue["id"], venue["mode"]) for venue in configurations] == [
        ("iclr", "final"),
        ("icml", "preprint"),
        ("neurips", "preprint"),
        ("acl", "final"),
        ("cvpr", "pagenumbers"),
        ("eccv", "final"),
    ]
    assert all(v["mode"] == "review" for v in original["venues"])
    iclr = paper_source(configurations[0], ["ref0001"])
    assert r"\iclrfinalcopy" in iclr
    assert r"\usepackage[preprint]{icml2026}" in paper_source(configurations[1], ["ref0001"])
    assert r"\usepackage[final]{acl}" in paper_source(configurations[3], ["ref0001"])
    assert r"\usepackage[pagenumbers]{cvpr}" in paper_source(configurations[4], ["ref0001"])
