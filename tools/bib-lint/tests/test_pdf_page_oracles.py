"""Physical gold comes from native PDF geometry, independently of product extraction."""

from pathlib import Path

import pytest
from pdf_e2e.pages import page_anchors
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, FloatObject, NameObject, NullObject
from reportlab.pdfgen import canvas


def _project(tmp_path, destinations):
    project = tmp_path / "paper"
    project.mkdir()
    pdf = canvas.Canvas(str(project / "main.pdf"), pagesize=(600, 800))
    pdf.drawString(60, 700, "Body cites Ada Example (2024).")
    pdf.showPage()
    pdf.drawString(60, 740, "References")
    if destinations:
        pdf.bookmarkHorizontalAbsolute("cite.ref0001", 704, left=60)
    pdf.drawString(60, 700, "[1] Ada Example. An independent title.")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(400, 699, "072")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(80, 685, "A second bibliography line.")
    if destinations:
        pdf.bookmarkHorizontalAbsolute("cite.ref0002", 654, left=320)
    pdf.drawString(320, 650, "[2] ????")
    if destinations:
        pdf.bookmarkHorizontalAbsolute("cite.ref0003", 604, left=320)
    pdf.drawString(320, 600, "[3]")
    pdf.save()
    if destinations:
        writer = PdfWriter(clone_from=project / "main.pdf")
        for key, left, top in [("ref0001", 60, 704), ("ref0002", 320, 654), ("ref0003", 320, 604)]:
            writer.add_named_destination_array(
                "cite." + key,
                ArrayObject(
                    [
                        writer.pages[1].indirect_reference,
                        NameObject("/XYZ"),
                        FloatObject(left),
                        FloatObject(top),
                        NullObject(),
                    ]
                ),
            )
        writer.write(project / "main.pdf")
    return project


@pytest.mark.parametrize("destinations", [True, False])
def test_native_reference_starts_have_tight_physical_first_line_boxes(tmp_path, destinations):
    project = _project(tmp_path, destinations)
    anchors = page_anchors(
        project,
        ["ref0001", "ref0002"],
        {
            "ref0001": "Ada Example. An independent title. A second bibliography line.",
            "ref0002": "????",
        },
    )
    first = anchors["ref0001"]
    assert first["page"] == 2
    assert first["text"] == "[1] Ada Example. An independent title."
    assert first["box"][0] == pytest.approx(60)
    assert first["box"][1] == pytest.approx(90.484)
    assert 200 < first["box"][2] < 300
    assert first["box"][3] - first["box"][1] == pytest.approx(12)
    assert anchors["ref0002"]["text"] == "[2] ????"
    assert anchors["ref0002"]["box"][0] == pytest.approx(320)


def test_native_numeric_empty_label_is_visible_but_unprinted_empty_item_is_omitted(tmp_path):
    anchors = page_anchors(
        _project(tmp_path, True), ["ref0003", "ref0004"], {"ref0003": "", "ref0004": ""}
    )
    assert anchors["ref0003"]["text"] == "[3]"
    assert "ref0004" not in anchors


def test_missing_nonempty_native_body_is_an_oracle_error(tmp_path):
    with pytest.raises(ValueError, match="ref0001"):
        page_anchors(_project(tmp_path, False), ["ref0001"], {"ref0001": "Invented author"})


def test_page_oracle_does_not_import_the_product_parser_or_layout():
    source = (Path(__file__).parent / "pdf_e2e/pages.py").read_text()
    assert "from bib_lint" not in source
    assert "import bib_lint" not in source


def test_year_leading_bodies_and_author_year_labels_are_native_text(tmp_path):
    project = tmp_path / "year-paper"
    project.mkdir()
    pdf = canvas.Canvas(str(project / "main.pdf"), pagesize=(600, 800))
    pdf.drawString(60, 740, "References")
    pdf.drawString(60, 700, "2025. Measuring ability. A report.")
    pdf.drawString(60, 650, "[Example et al., 2024] Ada Example. A title.")
    pdf.save()
    anchors = page_anchors(
        project,
        ["ref1", "ref2"],
        {"ref1": "2025. Measuring ability. A report.", "ref2": "Ada Example. A title."},
    )
    assert anchors["ref1"]["text"].startswith("2025.")
    assert anchors["ref2"]["text"].startswith("[Example et al., 2024]")
