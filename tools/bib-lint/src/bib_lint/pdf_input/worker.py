"""Disposable local parser process; owns no workspace and never retrieves links."""

import io
import json
import logging
import sys
import time

import pdfplumber

from bib_lint.pdf_input import PDFExtractionError
from bib_lint.pdf_input.citations import parse_reference
from bib_lint.pdf_input.layout import HEADING, _end, bibliography_lines, occurrences, page_lines
from bib_lint.pdf_input.streams import bounded_streams, decoded_stream_size


def _uris(group, hyperlinks):
    return [
        uri
        for uri in hyperlinks
        if any(_covers_line(uri, line) for line in group)
    ]


def _covers_line(uri, line):
    height = min(uri["bottom"] - uri["top"], line["bottom"] - line["top"])
    overlap = min(uri["bottom"], line["bottom"]) - max(uri["top"], line["top"])
    return (
        uri["page"] == line["page"]
        and height > 0
        and overlap > height / 2
        and min(uri["x1"], line["x1"]) > max(uri["x0"], line["x0"])
    )


def _page(page, limits, start, number_styles):
    if time.monotonic() - start > limits["max_seconds"]:
        raise ValueError("PDF extraction exceeds max_seconds resource limit")
    decoded = 0
    for stream in page.page_obj.contents:
        decoded += decoded_stream_size(stream, limits["max_decoded_bytes"] - decoded)
    if decoded > limits["max_decoded_bytes"]:
        raise ValueError("PDF exceeds max_decoded_bytes resource limit")
    lines = page_lines(page, number_styles)
    uris = []
    for link in page.hyperlinks:
        if not link.get("uri"):
            continue
        uris.append(
            {
                "uri": link["uri"],
                "page": page.page_number,
                **{
                    k: min(max(0, link[k]), page.width if k.startswith("x") else page.height)
                    for k in ("x0", "x1", "top", "bottom")
                },
            }
        )
    return lines, uris, decoded


def extract(raw, limits):
    with bounded_streams(limits["max_decoded_bytes"]):
        return _extract(raw, limits)


def _extract(raw, limits):
    start = time.monotonic()
    with pdfplumber.open(io.BytesIO(raw)) as document:
        if document.doc.encryption is not None:
            raise ValueError("Encrypted PDF is unsupported; supply a readable unencrypted PDF")
        if not 0 < len(document.pages) <= limits["max_pages"]:
            raise ValueError("PDF exceeds max_pages resource limit or has no pages")
        pages, hyperlinks, sizes, image_pages = [], [], [], []
        decoded_total, chars = 0, 0
        number_styles = set()
        for page in document.pages:
            lines, uris, decoded = _page(page, limits, start, number_styles)
            decoded_total += decoded
            chars += sum(len(line["text"]) for line in lines)
            if decoded_total > limits["max_decoded_bytes"] or chars > limits["max_text_chars"]:
                raise ValueError("PDF exceeds decoded content or extracted text resource limit")
            image_pages.extend(
                {"page": page.page_number, "top": image["top"], "bottom": image["bottom"]}
                for image in page.images
            )
            pages.append(lines)
            hyperlinks.extend(uris)
            sizes.append({"width": page.width, "height": page.height})
            page.close()
        try:
            lines, diagnostics = bibliography_lines(pages)
        except ValueError as error:
            if image_pages:
                raise PDFExtractionError(
                    "No readable bibliography; image pages may require OCR",
                    _unreadable(image_pages),
                ) from error
            raise
        groups = occurrences(lines)
        if not groups:
            if image_pages:
                raise PDFExtractionError(
                    "No readable reference occurrences; OCR required", _unreadable(image_pages)
                )
            raise ValueError("No reference occurrences found in bibliography")
        if len(groups) > limits["max_references"]:
            raise ValueError("PDF exceeds max_references resource limit")
        items = [
            parse_reference(group, f"pdf-ref-{i:04d}", _uris(group, hyperlinks))
            for i, group in enumerate(groups, 1)
        ]
        reference_pages = sorted({line["page"] for line in lines})
        unreadable = _reference_images(pages, lines, image_pages)
        diagnostics.extend(_unreadable(unreadable))
        reference_pages = sorted(set(reference_pages + unreadable))
        return {
            "schema_version": 4,
            "source": {"name": "", "sha256": ""},
            "items": items,
            "summary": {"total_count": len(items), "total_not_used": None},
            "verification_scope": {
                "mode": "all",
                "eligible_keys": [i["entry"]["key"] for i in items],
            },
            "extraction": {
                "schema_version": 1,
                "document": {"pages": len(sizes), "page_sizes": sizes},
                "state": "needs_review" if diagnostics else "complete",
                "reference_pages": reference_pages,
                "unresolved_fragments": len(unreadable),
                "diagnostics": diagnostics,
            },
        }


def main():
    logging.disable(logging.CRITICAL)
    limits = json.loads(sys.argv[1])
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (int(limits["max_seconds"]) + 1,) * 2)
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024,) * 2)
        payload = extract(sys.stdin.buffer.read(limits["max_bytes"] + 1), limits)
    except Exception as error:
        message = _error_message(error)
        payload = {
            "error": message,
            "diagnostics": getattr(error, "diagnostics", None)
            or [{"code": "pdf_extraction_failed", "message": message}],
        }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def _error_message(error):
    chain = error
    while chain is not None:
        if "password" in type(chain).__name__.lower():
            return "Encrypted PDF is unsupported; supply a readable unencrypted PDF"
        if isinstance(chain, ValueError) and "resource limit" in str(chain):
            return str(chain)
        chain = chain.__context__
    return (
        str(error)
        if isinstance(error, ValueError)
        else ("Corrupt or unreadable PDF; supply a readable research paper")
    )


def _unreadable(pages):
    numbers = sorted({page if isinstance(page, int) else page["page"] for page in pages})
    return [
        {
            "code": "unreadable_reference_page",
            "page": page,
            "message": "An image region in the reference list requires OCR or coverage review",
        }
        for page in numbers
    ]


def _reference_images(pages, references, images):
    flattened = [line for page in pages for line in page]
    first_heading = next(line for line in flattened if HEADING.fullmatch(line["text"].strip()))
    last_reference = flattened.index(references[-1])
    boundary = next((line for line in flattened[last_reference + 1 :] if _end(line)), None)
    selected = set()
    for image in images:
        if image["page"] < first_heading["page"] or (
            image["page"] == first_heading["page"] and image["bottom"] <= first_heading["bottom"]
        ):
            continue
        if boundary and (
            image["page"] > boundary["page"]
            or (image["page"] == boundary["page"] and image["top"] >= boundary["top"])
        ):
            continue
        selected.add(image["page"])
    return sorted(selected)


if __name__ == "__main__":
    main()
