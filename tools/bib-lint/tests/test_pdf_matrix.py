"""Build-negative cases stay visible and cannot hide unrelated build failures."""

from pdf_e2e.build import FIXTURES, read_json


def test_every_build_negative_names_an_original_case():
    from pdf_e2e.matrix import excluded_cases

    templates = read_json(FIXTURES / "templates.json")
    corpora = read_json(FIXTURES / "corpora/manifest.json")["corpora"]
    for venue in templates["venues"]:
        for corpus in corpora:
            negatives = excluded_cases(venue, corpus["id"])
            assert set(negatives) <= set(corpus["entry_keys"])
            assert all(case["diagnostic"] and case["reason"] for case in negatives.values())
    iclr = next(v for v in templates["venues"] if v["id"] == "iclr")
    assert len(excluded_cases(iclr, "adversarial")) == 2
    assert excluded_cases(iclr, "representative-20") == {}


def test_only_the_expected_compiler_diagnostic_confirms_a_negative(tmp_path):
    from pdf_e2e.matrix import expected_failure

    (tmp_path / "pass-2.log").write_text("Unrelated missing package")
    negatives = {"case": {"diagnostic": "has a comma at the end"}}
    assert expected_failure(tmp_path, negatives) is False
    (tmp_path / "pass-2.log").write_text("Name 1 has a comma at the end for entry ref0001")
    assert expected_failure(tmp_path, negatives) is True
