# bib-lint

Audit references from local BibTeX files or research-paper PDFs against independent
scholarly sources, then inspect comparisons and original evidence in a local UI.
Input PDFs, bibliographies, and compiled AUX files are never edited. Requires
Python 3.12+ and macOS/Linux. PDF extraction runs locally in a bounded Python worker;
no parser service, API key, Docker, or TeX installation is required at runtime.

Verification preserves structured author names and checks every supplied scholarly
locator, including secondary aliases and version pins. Conflicting `journal` and
`booktitle` fields, malformed locators, and unverified secondary identifiers remain
visible as findings. Local contradictions still require review when sources are
unavailable. Metadata checks do not assess scientific claim support, pages, volume,
or edition.

Run with UVX, which keeps tool dependencies outside your paper's environment:

```sh
uvx sciskill bib-lint verify /path/to/references.bib --aux /path/to/paper.aux
uvx sciskill bib-lint view /path/to/references.bib-lint
```

Without `--aux`, verification checks all entries and leaves citation usage unknown.
The default audit directory is `<input-stem>.bib-lint` beside the input. It contains
the report, resumable checkpoint, and integrity-checked cached evidence. Use
`--output DIRECTORY` to select another location and `--json` for a structured final
result; check its `status` and `complete` fields for partial or interrupted runs.
Repeating the verification command resumes unfinished work and preserves saved outcomes,
including source failures. Use `--refresh` to retry failures (`--key KEY` limits the
recheck to one reference). `--refresh` fetches
selected evidence again.

## Research-paper PDFs

```sh
uvx sciskill bib-lint verify "/path/to/research paper.PDF" --json
uvx sciskill bib-lint view "/path/to/research paper.bib-lint"
uvx sciskill bib-lint verify "/path/to/research paper.PDF" \
  --output /path/to/audit --key pdf-ref-0007 --refresh --json
```

PDF input audits the paper's **reference list**. It does not check the input paper's
own citation metadata or whether a citation supports a scientific claim. Use PDFs
with readable embedded text. OCR is not included; image regions in the reference
list and ambiguous bibliography coverage receive explicit diagnostics. Password-
protected, corrupt, empty, and unsupported PDFs fail before scholarly lookups.

The extractor handles numbered and author/year reference lists, column and page
continuations, and reference lists before appendices. It retains uncertain metadata
for review. Missing authors, titles, or identifiers remain missing; retrieved source
records never fill the input citation before comparison. Bibliography styles can
omit source fields, truncate authors, or abbreviate names. Information absent from
both printed text and relevant URI annotations cannot be recovered from the PDF.

All extracted occurrences are eligible for verification; citation usage remains
unknown. Generated keys such as `pdf-ref-0007` identify occurrences in extraction
order, including duplicate works. These keys are separate from printed labels and
original BibTeX keys. `--aux`, `--encoding`, and `--include-source` are rejected for
PDF inputs. Uppercase `.PDF` extensions and paths containing spaces are accepted.

PDF reports use schema 4 and retain the original PDF hash, parser versions/settings,
original fragments, URI targets, field evidence, and physical page numbers. Boxes
use PDF points from the top-left corner of each page. The viewer shows printed text
and hyperlink targets separately; extraction never follows annotation targets or
executes embedded PDF actions. Older schema-2/3 reports remain readable.

The final JSON includes an `extraction` summary. Its `state` describes bibliography
coverage; the existing `complete` flag describes source-verification progress.
A completed lookup run can still have extraction coverage `needs_review`. Inspect
both, together with per-reference diagnostics. Uncertain interpretation blocks
Correct; a reliably extracted mismatch can remain Invalid despite an unrelated
warning. A source outage does not establish that a reference is invalid.

Resume reuses sealed extraction only for unchanged PDF bytes, parser versions, and
settings. A changed PDF or parser requires a new output directory, even if its
citations look identical. `--refresh` repeats source verification and preserves the
saved extraction. Parse only in the viewer stays offline and does not create a
source-response cache; Verify performs the normal scholarly-source lookups.

Default extraction limits are 32 MiB input, 200 physical pages, 64 MiB decoded PDF
streams, 1,000,000 extracted text characters, 3,000 references, and 60 seconds. The
parent process enforces the wall-clock deadline; the worker also has a CPU limit
and a 1.5 GiB address-space limit on Linux. Flate, ASCII85, and ASCIIHex compression
receive bounded decoding across page content, forms, fonts, and object streams.
Other content compression receives a controlled unsupported-input failure.

## Local viewer

`bib-lint view` also starts without a path. Its local browser interface can parse,
verify, open, stop, and resume audits. Reload rereads saved results; Recheck sources
performs new lookups. The interface uses a loopback Python server and bundled
HTML/CSS/JavaScript with no frontend installation. Use `--port PORT` or
`--no-browser` when needed.

Agent assessments are read separately from `report.agent.json` inside an audit
directory (or `<report-stem>.agent.json` for a report file). They are bound to exact
entry hashes and never replace automated consensus. Evidence paths can be selected
in Audit setup. The browser displays comparisons, proposed corrections, primary
source links, and checksum-verified cached responses; it does not edit the
bibliography.

For source development and checks, see [Contributing](../../CONTRIBUTING.md) and the
[PDF acceptance workflow](../../docs/pdf-reference-input.md).
