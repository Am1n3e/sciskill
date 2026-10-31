"""Resource boundaries apply before lookup, with controlled local extraction failures."""

import math
from types import SimpleNamespace

import pytest
from reportlab.pdfgen import canvas

from bib_lint.pdf_input import PDFExtractionError, extract_pdf
from bib_lint.scope import validate_report


def _paper(path, *, pages=1, references=1):
    output = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1, pageCompression=0)
    for index in range(pages):
        output.setFont("Times-Bold", 12)
        output.drawString(50, 700, "References" if index == 0 else "Reference continuation")
        output.setFont("Times-Roman", 10)
        for reference in range(references):
            output.drawString(
                50,
                670 - reference * 25,
                f"[{index * references + reference + 1}] Jane Smith. "
                "An Example Paper. Journal, 2025.",
            )
        output.showPage()
    output.save()
    return path


def test_pdf_byte_limit_accepts_exact_size_and_rejects_one_less(tmp_path):
    source = _paper(tmp_path / "paper.pdf")
    size = source.stat().st_size
    validate_report(extract_pdf(source, limits={"max_bytes": size}))
    with pytest.raises(PDFExtractionError, match="max_bytes"):
        extract_pdf(source, limits={"max_bytes": size - 1})


def test_pdf_page_and_reference_limits_are_inclusive(tmp_path):
    source = _paper(tmp_path / "paper.pdf", pages=2)
    report = extract_pdf(source, limits={"max_pages": 2, "max_references": 2})
    assert report["extraction"]["document"]["pages"] == 2
    assert len(report["items"]) == 2
    with pytest.raises(PDFExtractionError, match="max_pages"):
        extract_pdf(source, limits={"max_pages": 1})
    with pytest.raises(PDFExtractionError, match="max_references"):
        extract_pdf(source, limits={"max_references": 1})


@pytest.mark.parametrize("limits", [{"max_text_chars": 1}, {"max_decoded_bytes": 1}])
def test_text_and_decoded_content_limits_fail_explicitly(tmp_path, limits):
    source = _paper(tmp_path / "paper.pdf")
    with pytest.raises(PDFExtractionError, match="resource limit"):
        extract_pdf(source, limits=limits)


@pytest.mark.parametrize(
    "limits",
    [
        {"max_bytes": 1.5},
        {"max_pages": 1.5},
        {"max_references": float("nan")},
        {"max_seconds": float("inf")},
        {"max_seconds": True},
        {"unknown_limit": 1},
    ],
)
def test_invalid_limits_are_controlled_before_worker_start(tmp_path, monkeypatch, limits):
    source = _paper(tmp_path / "paper.pdf")
    monkeypatch.setattr(
        "bib_lint.pdf_input.subprocess.run",
        lambda *a, **k: pytest.fail("Invalid limits reached the worker"),
    )
    with pytest.raises(PDFExtractionError, match="limit"):
        extract_pdf(source, limits=limits)


def test_parent_wall_clock_timeout_stops_worker_and_preserves_input(tmp_path, monkeypatch):
    import subprocess

    source = _paper(tmp_path / "paper.pdf")
    before = source.read_bytes()

    def timeout(*args, **kwargs):
        assert math.isfinite(kwargs["timeout"]) and kwargs["timeout"] > 0
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr("bib_lint.pdf_input.subprocess.run", timeout)
    with pytest.raises(PDFExtractionError, match="max_seconds"):
        extract_pdf(source)
    assert source.read_bytes() == before


@pytest.mark.parametrize("stdout", [b"bad JSON", b"[]", b"{}", b"null"])
def test_malformed_worker_results_are_controlled_failures(tmp_path, monkeypatch, stdout):
    source = _paper(tmp_path / "paper.pdf")
    monkeypatch.setattr(
        "bib_lint.pdf_input.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=stdout),
    )
    with pytest.raises(PDFExtractionError, match="result"):
        extract_pdf(source)


def test_deflate_content_is_bounded_before_pdfminer_allocates_the_decoded_stream():
    import tracemalloc
    import zlib

    from bib_lint.pdf_input.worker import decoded_stream_size

    compressed = zlib.compress(b"A" * (10 * 1024 * 1024))

    class Stream:
        def get_rawdata(self):
            return compressed

        def get_filters(self):
            from pdfminer.psparser import LIT

            return [(LIT("FlateDecode"), {})]

        def get_data(self):
            pytest.fail("Unbounded full-stream decoding was reached")

    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="max_decoded_bytes"):
            decoded_stream_size(Stream(), 1024)
        _, peak = tracemalloc.get_traced_memory()
        assert peak < 2 * 1024 * 1024
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize("limits", [[], [1], True, "not settings", {"max_bytes": 2**100}])
def test_limit_settings_require_a_small_typed_mapping(tmp_path, limits):
    source = _paper(tmp_path / "paper.pdf")
    with pytest.raises(PDFExtractionError, match="limit"):
        extract_pdf(source, limits=limits)


def test_worker_does_not_import_a_package_from_the_papers_directory(tmp_path, monkeypatch):
    source = _paper(tmp_path / "paper.pdf")
    impostor = tmp_path / "bib_lint"
    impostor.mkdir()
    (impostor / "__init__.py").write_text(
        "from pathlib import Path\nPath('unexpected-import').write_text('executed')\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    report = extract_pdf(source)
    assert len(report["items"]) == 1
    assert not (tmp_path / "unexpected-import").exists()
