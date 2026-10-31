# PDF reference auditing: implementation checklist

Specification: [PDF reference input](../SPEC-pdf-reference-input.md).
Architecture and reproducible commands: [PDF guide](../docs/pdf-reference-input.md).

The implementation follows the approved thin-slice TDD plan. UAI and OCR are
explicitly deferred. The earlier bibliography fixtures remain unchanged. Generated
projects, PDFs, compiler logs, caches, and audit reports stay under ignored
`.local/pdf-e2e/`.

| Task | Implementation and verification | State |
| --- | --- | --- |
| T01: Freeze the earlier bibliography cases | Exact 20/31/35-entry inputs, SHA-256 inventory, 86 case designs, 24 independently curated source records | Complete |
| T02: Pin official conference templates | 12 venue configurations, nine checksum-verified official assets, immutable TeX image | Complete |
| T03: Generate and compile projects | All 36 original cells accounted for; isolated native build negatives, renderable subsets, and positive counterparts | Complete |
| T04, T04a–d: Rendering gold | Native bibliography order, field visibility, author presentation, omitted information, and independently measured physical PDF evidence | Final validation |
| T05: Controlled scholarly HTTP | Protocol-shaped replay for the six real adapters, canonical facts independent of mutations, unexpected requests rejected | Complete |
| T06: PDF-only E2E harness | Public CLI, actual isolated worker, protected source/truth files, real providers and consensus | Complete |
| T07: Select the local parser | Pinned pdfplumber, local bounded grammar, documented alternatives and measured limits | Complete |
| T08: PDF evidence/report boundary | Strict schema 4, physical page/box/span validation, sealed evidence and content/version/settings identity; schemas 2/3 retained | Complete |
| T09: First compiled-PDF CLI slice | Clean and visibly corrupt compiled references through extraction, verification, and persisted report | Complete |
| T10: Columns and pages | Unequal columns, hanging indents, cross-page continuations, repeated headers, review gutters and appendix boundaries | Complete |
| T11: Names and text | Initials, accents, ligatures, suffixes, corporate names, truncation, proved line-end hyphen presentation; original fragments preserved | Complete |
| T12: Locators | Printed and annotation evidence, versions, wrapped IDs, malformed/empty IDs and secondary conflicts | Complete |
| T13: Decision precedence | Uncertainty cannot fabricate Correct or Invalid; independent reliable mismatches retained | Complete |
| T14: Unsupported/bounded inputs | Corrupt/encrypted/image-only inputs, coverage diagnostics, byte/page/text/reference/time/decoded-stream limits | Complete |
| T15: Resume and refresh | Reuse unchanged sealed extraction; refresh lookups only; reject changed bytes/versions/settings/tampering without replacement | Complete |
| T16: CLI and packages | Uppercase/spaced paths, generated keys, structured final envelope, standalone/shared installation outside checkout | Complete |
| T17: Viewer APIs | Offline parse, same audit semantics, extraction coverage and original evidence | Complete |
| T18: Browser presentation | Actual PDF flow, page/field/URI evidence, separate coverage banner, inert untrusted content, keyboard and responsive checks | Complete |
| T19: Full matrix | 39 baseline acceptance PDFs and six held-out native modes; exact fields/findings, clean outcomes, occurrences and locations | Final validation |
| T20: CI/release gate | Offline checks, Linux/macOS packages, pinned compilation and baseline/stress tests; bounded failure artifacts | Branch validation |
| T21: Documentation and final checks | User/skill documentation, decision note, source-only public artifacts, independent review, builds and PR | Final validation |

The independent review found and reproduced worker import isolation, nested-stream
expansion, unequal-column, malformed-evidence, ambiguous-title and locator-loss
bugs. Each fix has a focused regression. A second review checks matrix completeness,
independent gold, source isolation, CI failure gates, and the public artifact scope.

## Verification commands

Run from `tools/bib-lint` unless marked as repository-root commands:

```sh
uv run --locked --group dev pytest -q -m 'not package and not pdf_e2e'
uv run --locked --group dev pytest -q tests/test_package.py
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev ruff check . --select C901 --ignore-noqa
uv build
```

Follow the [compiled-matrix commands](../docs/pdf-reference-input.md#reproduce-the-checks)
for official assets, offline compilation, and baseline/stress acceptance. Selecting
a matrix makes missing prerequisites, incomplete gold, changed PDF hashes, or
unaccounted builds failures. Build negatives and source fields lost in typesetting
are reported separately; neither counts as detecting a PDF citation error.

From the repository root:

```sh
uv run --no-project --with 'PyYAML>=6,<7' python -m unittest discover -s tools/sciskill/tests -v
uv build
git diff --check
```

## Completion checkpoints

- C1: Every original build has a compiled result or an attributed native failure;
  all supported renderable projects compile with unchanged source metadata.
- C2: Gold comes from source facts and native output, and every required project
  is represented exactly once; product input contains only the copied PDF.
- C3: Runtime installation needs Python dependencies only; original BibTeX and
  legacy-report behavior remain covered.
- C4: Layout, names, and locators retain original spans and exact intended findings.
- C5: Uncertainty, resource failures, workspace ownership, and recovery preserve
  source bytes and valid prior reports.
- C6: Installed CLI and viewer agree on PDF occurrences and evidence; completed
  verification cannot hide uncertain extraction coverage.
- C7: Full baseline/stress, regressions, package/browser/build/lint gates and
  independent review pass before the PR is reported ready.
