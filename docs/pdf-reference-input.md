# PDF reference extraction and acceptance tests

The PDF adapter reads a local research paper's bibliography and passes extracted
citations to the existing scholarly providers and consensus rules. Extraction is
local; verification makes the same scholarly-source requests as a BibTeX audit.
See the [user guide](../tools/bib-lint/README.md#research-paper-pdfs) for commands,
limits, supported inputs, and recovery behavior.

## Parsing decision

The runtime pins `pdfplumber==0.11.10` with its pinned `pdfminer.six` dependency for
character positions, fonts, and URI annotations. A bounded local citation grammar
uses those original fragments and common author/year, numbered, and author-label
conventions. It preserves uncertain fields instead of completing them from source
lookups. The worker ignores Python environment search paths and uses the installed package.
It is a disposable Python subprocess, started automatically by
the installed package; it is not a separately configured service.

The choices considered were:

| Candidate | Decision |
| --- | --- |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Selected: character/word geometry, fonts, and annotations are available together; MIT license and Python wheels support macOS/Linux. Its documentation targets machine-generated PDFs. |
| [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) | Useful for independent test construction and comparison; plain text alone does not provide the layout and font boundary evidence needed by this adapter. It remains a development dependency. |
| [AnyStyle](https://anystyle.io/) | Provides a local learned citation parser, but its documented installation requires Ruby and its PDF finder uses additional tools. It does not meet this version's self-contained Python installation contract. Its web service is not used. |
| [refextract](https://github.com/inspirehep/refextract) | Its documented macOS installation limitation, external PDF tool requirement, and GPL-2.0 distribution implications exclude it from this package's runtime. |

This is a bounded parser, not a universal citation model. A successfully recovered
reference boundary is separate from confidence in its individual fields. Unknown
names, missing metadata, clipping, ambiguous text, and competing locators remain
visible. Uncertain compared fields cannot establish an Invalid or Correct verdict;
a reliably recovered discrepancy in another field can still be Invalid.

The runtime dependency bounds include `cryptography>=48,<49`: version 48 has
binary wheels for Intel macOS as well as ARM macOS and Linux. The initially
resolved version 50 attempted a native Rust/OpenSSL build on Intel macOS. The
selected dependency set and both installed launchers were exercised locally;
CI also checks package installation on Linux and macOS.

The 39 compiled development projects measured at most 272,846 input bytes, four
physical pages, 71,489 decoded page-content bytes, and 12,675 text characters.
Twenty-reference ICLR and ICML extraction took 0.753 and 0.739 seconds on the
development Intel Mac. These are fixture measurements, not throughput promises.
The defaults leave room for ordinary longer papers: 32 MiB input, 200 pages,
64 MiB decoded streams, one million text characters, 3,000 references, and 60
seconds. Synthetic tests exercise each boundary and nested compressed forms.

## Independent test inputs

The fixtures under `tools/bib-lint/tests/fixtures/pdf/` preserve the earlier
20-reference representative, 31-rule, and 35-adversarial bibliographies byte for
byte. The input manifest records their hashes. `truth.json` stores independently
curated source facts and case intent, not copied verifier verdicts. Four
representative references explicitly lack curated primary-source coverage.

`templates.json` pins official author kits, selected files, bibliography styles,
and a test-only TeX image by digest. The required baseline contains 12 venue
configurations and 36 original projects. UAI is deferred by explicit user request.
Downloaded templates, generated LaTeX, PDFs, logs, previews, and run reports stay
under ignored `.local/pdf-e2e/`; no vendor archive or response-capture tree belongs
in the public repository.

Some deliberately malformed citations prevent a native style from compiling.
`build_cases.json` records those exact cases or combinations. The build ledger
retains the original failures, checks isolated negative reproductions, and builds
explicitly named renderable subsets and positive counterparts. It never changes
a citation's fields or an official bibliography style to conceal an error.
A compilation failure is not a successful PDF issue detection.

Rendering expectations are fixed from the frozen source facts and native
bibliography output before running the product. The compact rendering manifests
identify source-case order, field visibility, PDF checksums, and build selections.
The oracle distinguishes printed fields, annotation-only fields, omitted source
information, and build negatives. Punctuation-only placeholders and visible empty
labels are retained as uncertain occurrences; they are not silently discarded.

## Reproduce the checks

From `tools/bib-lint` with Python 3.12+ and UV:

```sh
uv run --locked --group dev pytest -q -m 'not package and not pdf_e2e'
PYTHONPATH=tests uv run --locked --group dev python -m pdf_e2e.build --check-inputs
PYTHONPATH=tests uv run --locked --group dev python -m pdf_e2e.build --prepare-assets

# Docker and the pinned compiler are needed only for these test builds.
image=$(uv run --locked --group dev python -c \
  'import json; print(json.load(open("tests/fixtures/pdf/templates.json"))["toolchain"]["image"])')
docker pull --platform linux/amd64 "$image"
PYTHONPATH=tests uv run --locked --group dev python -m pdf_e2e.build --compile --matrix baseline
uv run --locked --group dev pytest -q -m pdf_e2e --pdf-matrix baseline
PYTHONPATH=tests uv run --locked --group dev python -m pdf_e2e.build --compile --matrix stress
uv run --locked --group dev pytest -q -m pdf_e2e --pdf-matrix stress
```

`--pdf-matrix pilot` runs the ICLR/ICML subset. Without a matrix selection, heavy
PDF tests are deselected. Once a matrix is selected, missing assets, incomplete
builds, changed PDF hashes, or missing gold fail; they never become optional skips.
The stress matrix uses six held-out native final/preprint/page-number modes.

Acceptance tests copy only the PDF into the product's working directory and call
the public CLI. A test-only access guard also runs in the parser subprocess and
rejects source BibTeX, BBL, AUX, or truth reads. Only scholarly HTTP transport is
controlled. Real provider routing, protocol parsing, identity matching, consensus,
workspace persistence, and final JSON remain in use. Unexpected requests fail.
Checks require the intended fields and findings, ordered occurrences, original
page evidence, and exact clean-control outcomes.

Fragment coordinates use PDF points from the top-left of the physical page:
`x0`, `top`, `x1`, `bottom`; page numbers are one-based. Independent gold anchors
come from the compiled PDF's original characters and native citation destinations,
with bibliography order from the native BBL. They do not call the product layout
or citation parser. Acceptance compares physical pages and fragment geometry as
well as metadata. The gold PDF checksum prevents applying anchors to another build.

## CI and artifact policy

The `Bibliography and PDF checks` workflow runs offline regressions, installed
packages on Linux/macOS, and the real compiled baseline/stress matrices. Release
publishing depends on the same reusable checks. A maintainer can make those status
checks mandatory through branch protection; adding a workflow does not change
repository protection settings.

Failure artifacts contain named ledgers, compiler logs, compiled test PDFs, JUnit
results, and audit reports/checkpoints for seven days. Raw response caches and
entire temporary workspaces are excluded. Template or bibliography changes require
checksum review and new rendering expectations; product failures do not justify
weakening gold labels or replacing a required finding with a generic review status.
