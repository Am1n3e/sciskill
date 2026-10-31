"""Compiler receipts must account for every rendered bibliography occurrence."""

import hashlib

import pytest


def _outputs(tmp_path, bibliography):
    (tmp_path / "main.pdf").write_bytes(b"%PDF-1.5\nminimal test output")
    (tmp_path / "main.bbl").write_text(bibliography)
    (tmp_path / "main.log").write_text("Output written on main.pdf\n")
    (tmp_path / "main.blg").write_text("Warning--empty year in ref0002\n")


def test_receipt_preserves_rendered_order_and_bibliography_warnings(tmp_path):
    from pdf_e2e.compiler import inspect_outputs

    _outputs(tmp_path, r"\bibitem[B(2024)]{ref0002} Two.\bibitem[A(2023)]{ref0001} One.")
    result = inspect_outputs(tmp_path, ["ref0001", "ref0002"])
    assert result["rendered_keys"] == ["ref0002", "ref0001"]
    assert result["warnings"] == ["Warning--empty year in ref0002"]
    assert result["pdf_sha256"] == hashlib.sha256((tmp_path / "main.pdf").read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "bibliography",
    [r"\bibitem{ref0001} One.", r"\bibitem{ref0001} One.\bibitem{ref0001} Duplicate."],
)
def test_receipt_rejects_missing_or_duplicate_occurrences(tmp_path, bibliography):
    from pdf_e2e.compiler import inspect_outputs

    _outputs(tmp_path, bibliography)
    with pytest.raises(ValueError, match="occurrence inventory"):
        inspect_outputs(tmp_path, ["ref0001", "ref0002"])


def test_receipt_rejects_undefined_citations_even_if_pdf_exists(tmp_path):
    from pdf_e2e.compiler import inspect_outputs

    _outputs(tmp_path, r"\bibitem{ref0001} One.")
    (tmp_path / "main.log").write_text("LaTeX Warning: Citation `ref0001' on page 1 undefined\n")
    with pytest.raises(ValueError, match="Unresolved"):
        inspect_outputs(tmp_path, ["ref0001"])


def test_changed_project_is_rejected_before_compiler_starts(tmp_path):
    import json

    from pdf_e2e.compiler import compile_project

    (tmp_path / "main.tex").write_text("changed")
    recipe = {"files": {"main.tex": "0" * 64}, "key_map": {"original": "ref0001"}}
    (tmp_path / "recipe.json").write_text(json.dumps(recipe))
    with pytest.raises(ValueError, match="Changed build input"):
        compile_project(tmp_path)


def test_cached_pdf_is_invalidated_when_output_changes(tmp_path):
    import json

    from pdf_e2e.compiler import _cached, inspect_outputs

    _outputs(tmp_path, r"\bibitem{ref0001} One.")
    receipt = inspect_outputs(tmp_path, ["ref0001"])
    receipt["fingerprint"] = "recipe-v1"
    (tmp_path / "build.json").write_text(json.dumps(receipt))
    assert _cached(tmp_path, "recipe-v1") == receipt
    assert _cached(tmp_path, "recipe-v2") is None
    (tmp_path / "main.pdf").write_bytes(b"%PDF-1.5\nreplaced")
    assert _cached(tmp_path, "recipe-v1") is None
