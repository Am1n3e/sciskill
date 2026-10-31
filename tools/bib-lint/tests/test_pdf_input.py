"""PDF-only extraction contracts, independently typeset without bibliography sources."""

import pytest
from reportlab.pdfgen import canvas

from bib_lint.pdf_input import PDFExtractionError, extract_pdf


def paper(path, references, *, columns=False, appendix=False, link=None):
    page = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    page.setFont("Times-Bold", 14)
    page.drawString(50, 740, "A paper about learning")
    page.setFont("Times-Roman", 10)
    page.drawString(50, 720, "Body discussion that is not a bibliography.")
    page.setFont("Times-Bold", 12)
    page.drawString(50, 680, "References")
    for x, y, text in references:
        page.setFont("Times-Roman", 10)
        page.drawString(x, y, text)
    if link:
        page.linkURL(link, (50, 626, 520, 640), relative=0)
    if appendix:
        page.setFont("Times-Bold", 12)
        page.drawString(50, 450, "A Appendix")
        page.setFont("Times-Roman", 10)
        page.drawString(50, 430, "[99] This is body text, not another reference.")
    page.save()
    return path


def test_pdf_only_numbered_fields_and_original_evidence(tmp_path):
    path = paper(
        tmp_path / "paper.PDF",
        [
            (50, 660, "[1] Jane Smith and John Doe. An Example Paper."),
            (66, 647, "Example Journal, 2025. doi:10.1234/example."),
            (50, 620, "[2] Ana Garcia. A Different Paper. Example Journal, 2024."),
        ],
        appendix=True,
    )
    before = path.read_bytes()
    report = extract_pdf(path)
    assert report["schema_version"] == 4
    assert len(report["items"]) == 2
    first = report["items"][0]
    assert first["entry"]["key"] == "pdf-ref-0001"
    assert first["entry"]["fields"]["title"] == "An Example Paper"
    assert first["entry"]["fields"]["year"] == "2025"
    assert first["entry"]["fields"]["doi"] == "10.1234/example"
    assert first["entry"]["persons"]["author"][0]["last"] == ["Smith"]
    assert first["pdf"]["label"] == "1"
    assert first["pdf"]["fragments"][0]["page"] == 1
    assert "Jane Smith" in first["pdf"]["fragments"][0]["text"]
    assert all("Appendix" not in i["pdf"]["text"] for i in report["items"])
    assert "is_used" not in first["validations"]
    assert path.read_bytes() == before


def test_annotation_target_and_printed_url_remain_distinct(tmp_path):
    path = paper(
        tmp_path / "paper.pdf",
        [
            (50, 660, "[1] Jane Smith. An Example Paper. Example Journal, 2025."),
            (66, 634, "https://arxiv.org/abs/2406.12276v1"),
        ],
        link="https://arxiv.org/abs/2411.15124v5",
    )
    item = extract_pdf(path)["items"][0]
    assert item["pdf"]["uris"][0]["uri"] == "https://arxiv.org/abs/2411.15124v5"
    assert "2406.12276v1" in item["pdf"]["text"]
    assert any(d["code"] == "locator_conflict" for d in item["pdf"]["diagnostics"])


def test_unnumbered_author_year_entries_are_separate(tmp_path):
    path = paper(
        tmp_path / "paper.pdf",
        [
            (50, 660, "Jane Smith. 2025. An Example Paper. Example Journal."),
            (65, 647, "https://arxiv.org/abs/2406.12276v1"),
            (50, 620, "John Doe. 2024. A Different Paper. Example Journal."),
        ],
    )
    items = extract_pdf(path)["items"]
    assert len(items) == 2
    assert [i["entry"]["fields"]["title"] for i in items] == [
        "An Example Paper",
        "A Different Paper",
    ]


@pytest.mark.parametrize("raw", [b"", b"not a PDF", b"%PDF-1.5\ntruncated"])
def test_unreadable_pdf_fails_without_empty_success(tmp_path, raw):
    path = tmp_path / "paper.pdf"
    path.write_bytes(raw)
    with pytest.raises(PDFExtractionError) as error:
        extract_pdf(path)
    assert error.value.diagnostics


def test_no_bibliography_is_an_explicit_failure(tmp_path):
    path = tmp_path / "paper.pdf"
    page = canvas.Canvas(str(path))
    page.drawString(50, 750, "This document contains no reference list.")
    page.save()
    with pytest.raises(PDFExtractionError, match="bibliography"):
        extract_pdf(path)


def test_two_column_references_follow_columns_not_pdf_object_order(tmp_path):
    path = tmp_path / "columns.pdf"
    page = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    page.setFont("Times-Bold", 12)
    page.drawString(50, 720, "References")
    page.setFont("Times-Roman", 10)
    # Objects are intentionally emitted right column first.
    for x, y, text in [
        (325, 700, "[3] Anna Lee. Third Paper."),
        (341, 687, "Example Journal, 2023."),
        (325, 650, "[4] Mark Wu. Fourth Paper."),
        (341, 637, "Example Journal, 2022."),
        (50, 700, "[1] Jane Smith. First Paper."),
        (66, 687, "Example Journal, 2025."),
        (50, 650, "[2] John Doe. Second Paper."),
        (66, 637, "Example Journal, 2024."),
    ]:
        page.drawString(x, y, text)
    page.save()
    items = extract_pdf(path)["items"]
    assert [i["pdf"]["label"] for i in items] == ["1", "2", "3", "4"]
    assert [i["entry"]["fields"]["title"] for i in items] == [
        "First Paper",
        "Second Paper",
        "Third Paper",
        "Fourth Paper",
    ]


def test_wrapped_reference_continues_on_next_physical_page(tmp_path):
    path = tmp_path / "continued.pdf"
    page = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    page.setFont("Times-Bold", 12)
    page.drawString(50, 720, "References")
    page.setFont("Times-Roman", 10)
    page.drawString(50, 650, "[1] Jane Smith. First Paper. Example Journal, 2025.")
    page.drawString(50, 620, "[2] John Doe. Second Paper.")
    page.showPage()
    page.setFont("Times-Roman", 10)
    page.drawString(66, 720, "Example Journal, 2024. doi:10.1234/second.")
    page.drawString(50, 680, "[3] Anna Lee. Third Paper. Example Journal, 2023.")
    page.save()
    items = extract_pdf(path)["items"]
    assert len(items) == 3
    assert [f["page"] for f in items[1]["pdf"]["fragments"]] == [1, 2]
    assert items[1]["entry"]["fields"]["doi"] == "10.1234/second"


def test_unequal_columns_keep_all_reference_occurrences(tmp_path):
    path = tmp_path / "unequal-columns.pdf"
    page = canvas.Canvas(str(path), pagesize=(800, 792), invariant=1)
    page.setFont("Times-Bold", 12)
    page.drawString(40, 720, "References")
    page.setFont("Times-Roman", 10)
    for number in range(1, 5):
        y = 690 - 55 * (number - 1)
        page.drawString(
            40,
            y,
            f"[{number}] Jane Smith. A Comprehensive Study of Attention Networks "
            "and Models with Extensive Applications.",
        )
        page.drawString(50, y - 13, "Journal of Testing and Evaluation, 2025.")
    for number in range(5, 9):
        y = 690 - 55 * (number - 5)
        page.drawString(500, y, f"[{number}] John Doe. An Example Paper.")
        page.drawString(510, y - 13, "Journal, 2025.")
    page.save()
    report = extract_pdf(path)
    assert [item["pdf"]["label"] for item in report["items"]] == list(map(str, range(1, 9)))
    assert all(len(item["pdf"]["fragments"]) == 2 for item in report["items"])
