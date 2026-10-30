# Spec: Audit references from research-paper PDFs

Status: Gradual implementation authorized by the user. The agreed E2E approach is recorded below; citation-parser selection remains an evidence-driven decision in T07.

## Objective

A researcher with a paper PDF should be able to audit its reference list without finding the original BibTeX file. SciSkill extracts the bibliography locally, preserves what the paper actually prints, and checks the extracted metadata through the existing bib-lint verification and evidence workflow.

The feature audits the works listed in the bibliography. It does not audit the input paper's own bibliographic record or whether its citations support its scientific claims.

## Confirmed requirements and proposed scope

| Requirement | Basis |
| --- | --- |
| Extract and audit the PDF's reference list | Confirmed by the user |
| Extraction runs locally without a separate service | Confirmed by the user |
| Target ordinary research papers, especially arXiv papers | User context |
| First release supports PDFs with usable embedded text; OCR is deferred | Proposed scope, based on that context |
| Support the standalone CLI and existing local viewer | Proposed integration |
| Keep original reference text and physical page locations | Proposed evidence requirement |

arXiv generates PDFs from submitted TeX and requires machine-readable PDF submissions. This supports targeting text-based research PDFs first; it is not a guarantee that every downloaded paper extracts correctly. See [arXiv PDF guidance](https://info.arxiv.org/help/submit_pdf.html).

### First-release coverage

- Local PDF files with one- or two-column reference lists, including lists continuing across pages.
- Numbered references and unnumbered author/year references in common English-language research-paper styles. Names and titles may contain Unicode, accents, ligatures, initials, and punctuation.
- A main reference list followed by an appendix. Ambiguous or multiple bibliography sections require an explicit extraction diagnostic instead of silently choosing one and claiming full coverage.
- Reference metadata containing titles, structured authors, year, venue, DOI, arXiv identifiers and version pins, or locators for existing supported archives.
- Read, inspect, stop, resume, select a reference, and refresh source verification through the current audit workspace.

### Deferred

OCR, cloud extraction, required local model servers or containers, automatic arXiv URL downloads or source retrieval, in-text citation-to-reference mapping, AUX matching for PDF inputs, document editing, BibTeX export, and a reference-correction editor.

Illustrations or scanned figures do not by themselves make a paper unsupported. The relevant question is whether the reference-list pages have usable text. A bibliography page requiring OCR must be identified explicitly; an unreadable page must not disappear from the coverage summary.

## User workflow and commands

The following commands are proposed feature behavior; PDF input is not implemented yet.

```sh
# Audit every extracted reference. Source files remain unchanged.
uvx sciskill bib-lint verify /path/to/paper.pdf --output /path/to/paper.bib-lint --json

# Open the report, extraction diagnostics, and source evidence.
uvx sciskill bib-lint view /path/to/paper.bib-lint

# Resume unfinished work using saved extraction and verification outcomes.
uvx sciskill bib-lint verify /path/to/paper.pdf --output /path/to/paper.bib-lint --json

# Retry scholarly-source lookups for one extracted reference.
uvx sciskill bib-lint verify /path/to/paper.pdf --output /path/to/paper.bib-lint --key pdf-ref-0007 --refresh --json
```

The standalone `bib-lint` command accepts the same arguments. PDF inputs use the existing `<input-stem>.bib-lint` output-directory convention. An input path with spaces or an uppercase `.PDF` extension works.

`--key` accepts the stable generated reference key shown in the report. It does not mean a page number or the bibliography's printed label. `--aux`, `--encoding`, and `--include-source` remain BibTeX-specific and are rejected for PDF input before replacing existing output. Required PDF provenance is saved without `--include-source`.

In the viewer, the input field accepts a local PDF path. **Parse only** performs extraction without scholarly-source requests; **Verify** extracts and audits. The overview distinguishes extraction coverage from verification progress. Reference details show the printed label, extracted text, physical page numbers, extraction warnings, parsed fields, and the existing source comparisons.

## Behavioral contract

### 1. Extract the bibliography, preserving layout evidence

- Locate the bibliography using document text and layout, not a rule that assumes references occupy the final pages.
- Respect column reading order; exclude repeated page headers, footers, page numbers, body text, captions, and subsequent appendix content from reference strings.
- Join a reference that spans lines, columns, or pages while retaining its original fragments and their order. Dehyphenation and Unicode normalization must not overwrite those fragments.
- Preserve occurrence order and separate duplicate references, even when labels or metadata are identical. Do not use title, DOI, or printed label as a unique occurrence key.
- Assign deterministic keys such as `pdf-ref-0001` in reference-list reading order. The same bytes, extractor version, and settings produce the same keys and extraction result. Keys need not remain stable after the PDF changes.
- Retain uncertain boundaries and unparsed reference-like fragments with diagnostics. Do not drop them merely because metadata parsing fails.
- If the bibliography cannot be identified, fail with an actionable diagnostic. An empty extraction must not be treated as a successfully audited empty bibliography.

### 2. Parse the printed citation without filling it from lookup results

- Separate metadata extraction from scholarly-source retrieval. Both the PDF bytes and extracted reference strings stay local during extraction; no cloud parser or model API is required.
- Produce the existing entry shape: key, entry type, text-valued fields, and structured names. Keep provenance and extraction diagnostics alongside the entry.
- Each accepted field must be traceable to the original reference. Missing fields stay missing. A parser's guessed author/title/venue boundary remains uncertain.
- Preserve distinct printed locators, malformed identifiers, and version pins so existing consistency checks can inspect them. A correct DOI must not erase a conflicting printed arXiv ID or URL.
- Retain URI annotations associated with a reference as separate PDF evidence, distinguishing hyperlink targets from printed text. Do not follow those links during extraction. A locator absent from both the rendered text and relevant annotations cannot be inferred from the original BibTeX.
- Do not complete an input citation with retrieved canonical metadata and then compare that completed citation against the same source. Retrieved metadata remains source evidence and proposed corrections.
- Distinguish a field printed incorrectly from a field extracted ambiguously. Uncertain extraction alone cannot establish that the printed citation is invalid.

### 3. Integrate with existing verification decisions

- Audit scope is all extracted occurrences. Citation usage remains unknown; presence in the bibliography does not prove use in the body text.
- Reuse existing providers, matching, field comparisons, cache integrity checks, source-failure handling, and consensus rules.
- An unresolved extraction diagnostic affecting identity, boundaries, or a compared field prevents a **Correct** verdict. Identifiable references can still be looked up for review.
- A demonstrated discrepancy in a reliably extracted field may remain **Invalid** despite an unrelated extraction warning. Source outages remain source failures, not evidence of fabrication.
- A reference with insufficient trustworthy metadata remains **Needs review** or **Unresolved**, with its original text visible. It must not receive fabricated placeholder authors or titles to make it pass validation.
- A bibliography whose extraction coverage is uncertain is never described as “all PDF references verified,” even if every extracted entry has completed its source lookups.

### 4. Preserve provenance, checkpoints, and compatibility

PDF reports need a versioned contract for extraction evidence and its effect on verdicts. Proposed PDF report schema: version 4. Continue reading existing version-2 and version-3 BibTeX/JSON reports without inventing PDF provenance. Update validators, viewer, resume logic, and package tests together.

Minimum document provenance:

- Original PDF name and SHA-256, total physical page count, and identified reference-page ranges.
- Extractor/parser identifiers and versions, extraction settings, and versioned diagnostics.
- Extraction coverage state: `complete`, `needs_review`, or `failed`. “Complete” describes the extractor's supported checks, not a universal accuracy guarantee.

Minimum per-reference provenance:

- Generated key, original label when present, and ordered original text fragments.
- One-based physical PDF page numbers and fragment bounding boxes in a documented coordinate system.
- Normalized reference text, extracted field-to-fragment mappings, and structured diagnostic codes/messages.

Extraction evidence belongs in the audit workspace. Reference it with checksums if stored outside the report; report imports must retain or explicitly report missing evidence. Normalized entry data is not a replacement for the original reference text.

Workspace identity must include PDF byte hash, extraction settings, and extractor/parser versions in addition to entry/scope identity. A changed PDF is rejected in an occupied workspace even if its extracted citations happen to be identical. Parser/version changes must not silently reuse stale extracted fields or verdicts; require a new workspace for the first release. Resume must not rerun successful extraction when its inputs and versions are unchanged.

`--refresh` refreshes source verification, not extraction. Interrupted extraction can be rerun atomically from the unchanged PDF; interrupted verification resumes from the persisted extraction. Neither path may destroy a valid earlier report.

The CLI final-result envelope keeps its current fields and gains an extraction summary for PDF inputs: coverage state, extracted occurrence count, unresolved-fragment count, and diagnostics. Existing `complete` continues to describe verification work on report entries. A completed verification run can coexist with `extraction.state = needs_review`; JSON and viewer must expose both prominently. A failed extraction returns a failed command result and a nonzero exit status before any provider request.

### 5. Handle unsupported and damaged input explicitly

| Input or condition | Required result |
| --- | --- |
| Valid text-based bibliography | Extract occurrences and run the chosen viewer/verification action |
| Image-only reference pages or unusable text encoding | Identify affected physical pages and explain that OCR or a readable PDF is needed; never claim full coverage |
| No identifiable bibliography, or zero extracted references | Extraction failure; no source lookups and no empty-success report |
| Ambiguous bibliography boundaries or multiple lists | Visible coverage diagnostic and preserved candidate material; no silent full-coverage claim |
| Encrypted PDF requiring a password | Actionable unsupported-input failure; no password prompt or password storage in v1 |
| Corrupt, truncated, empty, or falsely named PDF | Controlled failure with the source and any existing workspace preserved |
| Input exceeds documented parser resource limits | Controlled resource-limit failure; no uncontrolled retry or service fallback |
| Interrupted lookup or provider outage | Existing checkpoint/resume behavior, with extraction evidence retained |

Keep limits on PDF bytes, pages, decoded content, extracted text, reference count, and extraction time explicit and testable. Their numeric defaults require measurement on the agreed corpus before implementation approval. Do not fetch links, execute PDF actions, or extract arbitrary embedded files while parsing the document.

## Tech stack and dependency decision

Keep the current Python 3.12+, `httpx`, `pybtex`, pytest, Ruff, and local HTML/CSS/JavaScript architecture. No frontend framework or separate parser service is required.

Use an in-process, layout-aware PDF library. `pdfplumber` is a candidate because it exposes text and geometric information; its documentation says it works best on machine-generated PDFs. `pypdf` is another local text-extraction candidate, but extracting text alone does not parse bibliographic fields. See [pdfplumber](https://github.com/jsvine/pdfplumber) and [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

The structured citation parser is an open technical decision. Do not assume a few regular expressions can reliably split every author/title/venue combination. Compare a bounded deterministic parser with an existing local parser against independently annotated examples. Select a dependency only after checking accuracy, macOS/Linux installation, license compatibility, and packaging requirements. A server, API key, or mandatory manual service startup fails the confirmed requirement. No dependency is added by this spec.

## Project structure and code style

Keep PDF input adaptation separate from provider retrieval and consensus. Suggested locations, subject to the later technical plan:

```text
tools/bib-lint/src/bib_lint/pdf_input/     PDF extraction, parsing, and provenance types
tools/bib-lint/src/bib_lint/audit.py       Input dispatch and workspace ownership
tools/bib-lint/src/bib_lint/scope.py       Versioned report validation and identity
tools/bib-lint/src/bib_lint/verification/  Extraction-aware comparison/decision integration
tools/bib-lint/src/bib_lint/viewer/        PDF setup and extraction evidence presentation
tools/bib-lint/tests/test_pdf_*.py         Unit and workflow contracts
tools/bib-lint/tests/fixtures/pdf/         Small synthetic PDFs and independent expectations
tools/sciskill/tests/                    Installed shared-launcher compatibility
skills/sciskill/references/bib-lint.md    Agent instructions for PDF inputs
```

Use existing snake_case naming, dataclasses for internal records, explicit validation at input/report boundaries, typed exceptions, and atomic JSON writes. Continue Ruff's 100-character line limit and McCabe complexity ceiling of 10. Existing style example from the audit boundary:

```python
@dataclass(frozen=True)
class Workspace:
    root: Path

    def active(self):
        return self.checkpoint if self.checkpoint.exists() else self.final
```

Avoid a second verifier inside the PDF extractor. Render extracted text as text in the viewer, not executable markup. Small helpers should express extraction steps rather than hide policy in regular expressions or exception handlers.

## Testing strategy and success criteria

Use TDD: establish independent expected reference boundaries, fields, provenance, and verdicts before implementing each behavior. Demonstrate that new behavior tests fail without the implementation. Never obtain expected values by calling the extractor or normalizer being tested.

| Test family | Required cases and assertions |
| --- | --- |
| Layout and boundaries | One/two columns; mixed column widths; wrapped and hanging-indent entries; cross-column/page continuations; bibliography before appendix; repeated headers/footers; numbered and author/year styles; multiple or missing headings |
| Text fidelity | Ligatures, Unicode normalization, accented names, initials, corporate authors, `et al.`, punctuation, line-end hyphens versus real identifier hyphens, wrapped DOI/URL strings, extraction order differing from PDF object order |
| Identity and uncertainty | Correct DOI with wrong title; conflicting secondary locators; pinned arXiv versions; missing fields; uncertain author/title splits; two references accidentally merged; one split in two; repeated labels and duplicate works kept as separate occurrences |
| Evidence and verdicts | Every accepted field maps to original fragments; uncertain extraction never becomes Correct; reliable mismatch versus extraction ambiguity; all providers unavailable; partial-author status combined with extraction warnings |
| Invalid input | Image-only/mixed reference pages, unreadable fonts, encrypted and corrupt files, empty PDF, wrong file type, no bibliography, resource-limit boundaries |
| Workspace and schema | Stable keys; same bytes under a renamed path; changed PDF with identical citations; source/output symlink and hardlink protection; interrupted writes; extraction and lookup interruption; stale parser version; malformed provenance JSON values; schema-2/3 compatibility |
| End to end | Synthetic PDF through actual extraction, CLI/viewer, independently controlled provider responses, persisted report, reload, resume, and selected-key refresh; verify original bytes remain unchanged |
| Distribution | Standalone wheel and shared `sciskill` package contain the adapter and install its dependencies on supported macOS/Linux environments; BibTeX-only use still works |

Build the primary acceptance corpus from the earlier 20-entry representative bibliography, 31 rule variants, and 35 adversarial cases. Render each bibliography through official conference LaTeX templates with deterministic generated research-paper text. The initial explicit venue list is NeurIPS, ICML, ICLR, AAAI, IJCAI, AISTATS, UAI, ACL, EMNLP, NAACL, CVPR, ICCV, and ECCV: 13 venues and 39 baseline project builds. Pin template releases, bibliography styles, compilation options, and the TeX toolchain. Shared template families still receive separate venue configurations.

The pipeline under test is LaTeX project → compiled PDF → actual PDF extraction and metadata parsing → existing verification → persisted report. Give the product only the PDF; keep `.bib`, `.bbl`, `.aux`, case identifiers, and expected answers in the test harness. Mock only the scholarly HTTP transport with controlled, independently curated responses; compilation, extraction, providers, comparison, and report generation run for real.

Before implementing extraction, establish independent per-template expectations for reference order, printed fields, original page locations, and required findings. Classify each source-case rendering as preserved in text, retained only in a URI annotation, partially preserved, omitted, or unable to compile. Freeze these classifications before evaluating the extractor. Omitted source metadata is not a PDF detection success or a parser failure; it remains an explicit coverage limitation. Compilation failures are build failures with case attribution, not successful PDF checks or silently skipped tests. If a source case needs TeX-safe build keys, record that mapping without changing its citation metadata or the frozen original bibliography.

Require the intended field-level finding, not merely any non-Correct verdict. Test clean controls and paired corruptions; identify missing and extra occurrences, merges, splits, ordering errors, and wrong provenance. Generate layout variants for wrapping, column/page transitions, headers/footers, appendix boundaries, and misleading citation-like body text. Keep the direct-BibTeX tests for source-only checks and use differential results for diagnosis, never as the sole expected-answer generator.

Public fixtures are synthetic or explicitly redistributable and include only the sources, compact response fixtures, manifests, and expectations needed to reproduce tests. Personal papers, large captured sources, generated PDFs, compiler logs, audit evidence, and benchmark outputs stay under ignored `.local/` storage or CI artifacts. Promotion of selected earlier corpus files must not restore the removed development/evidence tree wholesale.

For each supported acceptance fixture, every annotated occurrence must be represented once with correct boundaries and physical page provenance, or explicitly retained as unresolved with a diagnostic. Fully supported fixtures must extract the annotated fields correctly. Partial/unsupported fixtures must produce their expected warning or failure; a blanket “needs review” result is not a substitute for successful extraction on supported fixtures. Body/appendix text must not become a fabricated reference. No expected bad or uncertain case may be classified Correct. Do not make an accuracy-percentage claim beyond the measured corpus.

Before release, the new extraction and end-to-end tests, existing offline regression suite, installed-package tests, lint, formatting, and complexity checks must pass. Document any optional skips. Verify the real viewer displays original reference text, page provenance, coverage warnings, and unchanged source evidence.

Existing development check commands:

```sh
# From tools/bib-lint:
uv run --group dev pytest -q -m 'not package'
uv run --group dev pytest -q tests/test_package.py
uv run --group dev ruff check .
uv run --group dev ruff format --check .
uv run --group dev ruff check . --select C901 --ignore-noqa
uv build

# From the repository root:
uv run --no-project --with 'PyYAML>=6,<7' python -m unittest discover -s tools/sciskill/tests -v
uv build
```

## Boundaries

- **Always:** preserve source bytes and provenance; keep extraction local; validate PDF/report boundaries; retain uncertainty; use TDD and independent expectations; maintain existing verification behavior for BibTeX/JSON; keep research artifacts and local agent setup ignored.
- **Resolve during review:** first-release OCR scope; citation-parser dependency and installation footprint; concrete resource limits; report-schema and extraction-summary contract. A change to these approved requirements needs an updated spec before code changes.
- **Never:** upload PDF content for extraction by default; require an unapproved service; invent missing metadata; silently discard undecodable reference pages or unresolved occurrences; treat failed extraction as an empty successful audit; overwrite source files; remove failing tests to obtain green results.

## Open questions for review

1. Confirm the proposed first-release target: ordinary text-based research PDFs, with OCR deferred and unreadable reference pages flagged.
2. Choose the local citation-parser approach after evaluating annotated examples. The no-service requirement is settled; the package or local executable is not selected.
3. Validate the pinned official template assets, independent rendering expectations, and measured resource limits. The agreed first corpus will be generated by compiling the earlier bibliographies, rather than depending on a separately supplied PDF.

The implementation plan and ordered tasks live in `tasks/plan.md` and `tasks/todo.md`. Implement in verified increments and retain the explicit decision/review checkpoints.
