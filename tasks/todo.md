# Tasks: PDF reference auditing

Plan: [plan.md](plan.md). Specification: [PDF reference input](../SPEC-pdf-reference-input.md).

The user authorized gradual implementation. T01 is complete. T02 is complete for the 12 in-scope venues. UAI is deferred by explicit user instruction; the baseline is 36 projects. Commands below run from `tools/bib-lint` unless a repository-root command is explicitly marked. New test names, harness commands, markers, and options remain proposed outputs until their owning tasks are completed.

Each task follows red → green → refactor, preserves passing related regressions, and gets one focused commit after verification. Pure fixture/configuration/documentation tasks use content/build validation rather than invented behavioral tests. Do not mark a task complete while its expected behavior is skipped, xfailed, replaced by a stub, or merely covered by an unrelated Needs review verdict.

Generated projects, PDFs, build logs, temporary probes, and run output go under repository-root `.local/pdf-e2e/`. Paths below beginning `tests/`, `src/`, or `pyproject.toml` are relative to `tools/bib-lint`; paths marked `root:` are repository-relative. Likely file lists are budgets, not permission for adjacent refactoring. Split a task if it needs more than five changed source/configuration files.

## T01: Freeze the earlier bibliography cases

- [x] Complete T01.

**Description:** Prepare the three earlier corpora as reproducible input fixtures with independently curated canonical metadata and explicit case intent. Preserve original local copies and review the exact subset promoted into official tests.

**Acceptance criteria:**
- [x] Record hashes and 20/31/35-entry inventories, case IDs, mutations, expected fields/findings, and control outcomes; expectations do not derive from current verdicts.
- [x] Preserve metadata and literal source keys; record any later build-key mapping separately. Source-only checks are identified rather than silently discarded.
- [x] Promoted fixtures contain only the agreed sources and compact truth, with attribution where needed; no old development logs, evaluation history, or captured evidence tree is restored.

**Verification:** Compare inventory/hashes against the three `.local/bib-lint-development/tests/fixtures/e2e/` inputs; parse every entry with the existing parser; review the truth/case inventory before product work. T03 supplies the automated `--check-inputs` command.

**Dependencies:** None. **Estimated scope:** M, five fixture files.
**Files likely touched:** `tests/fixtures/pdf/corpora/{representative-20.bib,rule-variants.bib,adversarial.bib}`, `tests/fixtures/pdf/corpora/manifest.json`, `tests/fixtures/pdf/truth.json`.

**Completed verification:** All three copies match their original bytes, SHA-256, entry order/types, and 20/31/35 counts. All 86 case bindings and prior independently designed source expectations are retained. The 19 user-derived representative entries match the original 147-entry input; the official JMLR addition is attributed. Canonical facts contain 24 records, including ten checked directly against checksum-verified archived source metadata. Four references explicitly lack a curated primary fixture, five cases retain source-only key/AUX/cache checks, and all PDF expectations remain unset for T04. Existing offline suite: 989 passed, one optional skip, one package test deselected. Tool wheel/sdist build, Ruff lint/format/complexity, and fixture-integrity checks passed. No runtime behavior or dependency changed.

## T02: Pin official conference templates

- [x] Complete T02.

**Description:** Resolve the 12 venue configurations in the plan to official release assets, including their native bibliography styles and compilation recipes.

**Acceptance criteria:**
- [x] Every venue records a specific year/release or commit, official URL, SHA-256, template family, native bibliography style, supported mode, TeX engine, and attribution/asset policy.
- [x] Venue-specific configurations remain explicit even where ACL or CVPR families share assets; asset fetching rejects checksum drift and does not silently substitute a third-party template.
- [x] Resolve a reproducible TeX toolchain for development/CI; no compiler/container/service becomes a product runtime requirement.

**Verification:** Inspect each official author kit; verify asset checksums; resolve engine/package availability on the chosen test-build environment. T03 validates these pins through actual compilation.

**Dependencies:** None; can be prepared alongside T01. **Estimated scope:** S, two files.
**Files likely touched:** `tests/fixtures/pdf/templates.json`, `tests/fixtures/pdf/README.md`.

**Completed verification:** Nine official archives/commit snapshots have verified archive/member hashes and explicit recipes for all 12 required venues. UAI is deferred by explicit user instruction and is outside the 36-build baseline. The test-only Linux/amd64 TeX image is pinned by immutable platform digest; registry metadata and Docker availability were checked. Compiler execution and package availability will be verified by T03. No compiler becomes a product runtime dependency.

## T03: Generate and compile the LaTeX projects

- [ ] Complete T03.

**Description:** Build a test-only generator/compiler that combines each pinned template with each frozen corpus and deterministic research-paper body text.

**Acceptance criteria:**
- [ ] Expose `--check-inputs`, `--prepare-assets`, and `--compile --matrix baseline`; produce the 36 baseline projects using native styles, actual citation commands, and all corpus entries.
- [ ] Keep originals unchanged; record any TeX-safe key map, exact compile recipe, input/asset/toolchain hashes, bibliography warnings, and PDF checksum. Generated body text contains no case IDs, answer markers, or issue descriptions.
- [ ] Compilation is offline after asset preparation, shell escape is disabled, failures are attributed, and the build cache invalidates on any recipe change. Required supported builds cannot silently skip missing assets or failed references.

**Verification:** `PYTHONPATH=tests uv run --group dev python -m pdf_e2e.build --check-inputs`; run asset preparation, then `--compile --matrix baseline`; inspect representative rendered pages and `.bbl` occurrence counts/order. A failed build is not an extraction failure or a passing issue check.

**Dependencies:** T01, T02. **Estimated scope:** M, four files.
**Files likely touched:** `tests/pdf_e2e/{__init__.py,build.py,paper_body.tex}`, `tests/test_pdf_build.py`.

**Progress (T03a):** Added the input/template integrity command and five focused tests. They reject byte drift, missing case inventory, and unresolved required pins; the frozen 86-case / 36-build inventory passes. Asset preparation now verifies archives/members, rejects changed content and path escapes, and stages all nine official kits under ignored storage. Eight focused tests pass. Project generation and compiler execution are the next slice. T03 is split into independently committed validator, asset, generator, and compiler slices to keep each change reviewable.

## C1: Reproducible build checkpoint

- [ ] All 36 planned builds are accounted for, with each supported project compiling and any intrinsic build-negative case explicitly reviewed.
- [ ] Frozen inputs are unchanged, asset/toolchain pins are valid, and generated PDFs/logs are ignored.
- [ ] Representative bibliography pages visually match the native template, without hidden test answers or fixture shortcuts.

## T04: Annotate rendering visibility and PDF ground truth

- [ ] Complete T04.

**Description:** Define the rendering-oracle contract and annotate the ICLR/ICML pilot, before using a product extractor to evaluate them. T04a–d cover the other venues in separate focused batches.

**Acceptance criteria:**
- [ ] Classify every pilot corpus case as text, annotation-only, partial, omitted, or compile failure; record rendering order, label, physical pages, accepted field spans, and URI evidence where relevant. The format supports the same contract for all later batches.
- [ ] Required diagnostics and statuses are specific to what survives rendering. Source-only issues remain explicit limitations; partial cases name the fields still testable.
- [ ] Review gold annotations from rendered PDFs and source truth, not product extraction. Coordinates use a documented system/tolerance and are tied to the exact PDF build hash.

**Verification:** Independently inspect rendered pages/annotations; run `uv run --group dev pytest -q tests/test_pdf_oracles.py`; ensure the pilot inventory includes every planned corpus/case pair and no product-output-derived labels. The oracle loader validates the complete venue inventory after T04a–d.

**Dependencies:** T01, T03. **Estimated scope:** M, four files.
**Files likely touched:** `tests/fixtures/pdf/visibility/pilot.json`, `tests/fixtures/pdf/gold/pilot.json`, `tests/pdf_e2e/oracles.py`, `tests/test_pdf_oracles.py`.

## T04a: Review NeurIPS/AAAI/IJCAI gold renderings

- [ ] Complete T04a.

**Description:** Independently annotate the three corpus builds for each general-AI venue in this batch, using the T04 contract.

**Acceptance criteria:**
- [ ] Account for every NeurIPS/AAAI/IJCAI corpus/case pair, with original order/page evidence and pre-reviewed visibility classifications.
- [ ] Required fields/findings and clean outcomes follow rendered evidence, including native style omissions; product output never defines an expectation.
- [ ] The batch merges through the oracle validator without changing pilot expectations to accommodate a product result.

**Verification:** Inspect every reference-list page in the batch; run `uv run --group dev pytest -q tests/test_pdf_oracles.py`; check inventory completeness for these three venues.

**Dependencies:** T03, T04. **Estimated scope:** S, two data files.
**Files likely touched:** `tests/fixtures/pdf/visibility/general-ai.json`, `tests/fixtures/pdf/gold/general-ai.json`.

## T04b: Review AISTATS gold renderings

- [ ] Complete T04b.

**Description:** Independently annotate the statistical-ML conference batch, keeping default formatting and bibliography evidence intact.

**Acceptance criteria:**
- [ ] Account for every AISTATS corpus/case pair with ordered page/field evidence and reviewed visibility classifications.
- [ ] Distinguish abbreviation, omitted metadata, and actual printed corruption; no blanket uncertain outcome substitutes for a required finding.
- [ ] The batch passes the common gold validator without depending on a product extractor.

**Verification:** Inspect the batch's reference pages and URI annotations; run `uv run --group dev pytest -q tests/test_pdf_oracles.py`; check both venues' inventories.

**Dependencies:** T03, T04. **Estimated scope:** S, two data files.
**Files likely touched:** `tests/fixtures/pdf/visibility/statistical-ml.json`, `tests/fixtures/pdf/gold/statistical-ml.json`.

## T04c: Review ACL/EMNLP/NAACL gold renderings

- [ ] Complete T04c.

**Description:** Independently annotate the NLP batch, retaining separate configurations even where a common style family produces similar output.

**Acceptance criteria:**
- [ ] Account for all three venues' corpus/case pairs; verify actual rendered order, fields, physical pages, and relevant annotations.
- [ ] Shared style behavior can share reviewed rules, but one venue's PDF coordinates are never copied onto another without checking its exact build.
- [ ] Clean and corrupted expectations are fixed before product evaluation, with omissions and truncations explicit.

**Verification:** Inspect reference pages for every venue/corpus build; run `uv run --group dev pytest -q tests/test_pdf_oracles.py`; verify separate venue coverage.

**Dependencies:** T03, T04. **Estimated scope:** S, two data files.
**Files likely touched:** `tests/fixtures/pdf/visibility/nlp.json`, `tests/fixtures/pdf/gold/nlp.json`.

## T04d: Review CVPR/ICCV/ECCV gold renderings

- [ ] Complete T04d.

**Description:** Independently annotate the vision batch, including the distinct ECCV kit and the CVPR/ICCV family configurations.

**Acceptance criteria:**
- [ ] Account for every venue/corpus/case pair and actual column/reading order, with physical page/field evidence and frozen visibility classifications.
- [ ] Verify numbered labels, rendered author abbreviations, locator availability, and URI targets from the actual PDFs rather than template-name assumptions.
- [ ] Complete the full 12-venue inventory without changing labels to match a product result.

**Verification:** Inspect the batch's reference pages/annotations; run `uv run --group dev pytest -q tests/test_pdf_oracles.py`; require all 36 baseline build identities and every case rendering to be accounted for.

**Dependencies:** T03, T04. **Estimated scope:** S, two data files.
**Files likely touched:** `tests/fixtures/pdf/visibility/vision.json`, `tests/fixtures/pdf/gold/vision.json`.

## T05: Supply controlled scholarly HTTP responses

- [ ] Complete T05.

**Description:** Feed real built-in provider adapters deterministic protocol responses from the independently curated canonical metadata.

**Acceptance criteria:**
- [ ] Support the providers required by the corpus, including primary/secondary identities, version pins, conflicts, outages, and incomplete searches.
- [ ] Canonical responses never derive from corrupted input metadata; unexpected requests and external network access fail visibly.
- [ ] Response data is compact and sufficient for real provider routing/parsing; do not replace providers, matching, or consensus with test decisions.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_http_replay.py`; introduce an unexpected query and verify rejection; prove a deliberately wrong title remains different from canonical truth.

**Dependencies:** T01; can run alongside T04 after the truth contract is fixed. **Estimated scope:** M, three files.
**Files likely touched:** `tests/pdf_e2e/http_replay.py`, `tests/fixtures/pdf/source_records.json`, `tests/test_pdf_http_replay.py`.

## T06: Establish the failing PDF-only E2E harness

- [ ] Complete T06.

**Description:** Run the actual CLI entry point in an isolated test process with compiled PDF input, controlled HTTP transport, and an exact report oracle.

**Acceptance criteria:**
- [ ] The product working directory contains no `.bib`, `.bbl`, `.aux`, case map, or expected answers. A test-only access check rejects product reads of those harness inputs.
- [ ] Real compilation/extraction/provider/decision/report paths remain in use; only the HTTP transport is controlled. No production bypass flags or fake provider registry is introduced.
- [ ] Register `pdf_e2e` and `--pdf-matrix`; heavy cases are deselected without explicit matrix selection, while a selected matrix fails on missing prerequisites. Pilot tests fail against current unsupported-PDF behavior with distinct failure categories and no blanket xfail.

**Verification:** `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix pilot` must demonstrate the expected initial red result; run a harness self-test that would detect source-file leakage. Confirm the existing fast tests still collect without TeX.

**Dependencies:** T03, T04, T04a, T04b, T04c, T04d, T05. **Estimated scope:** M, four files.
**Files likely touched:** `tests/pdf_e2e/runner.py`, `tests/test_pdf_e2e.py`, `tests/conftest.py`, `pyproject.toml`.

## C2: Independent-oracle checkpoint

- [ ] Every case has a reviewed rendering outcome and expected finding; missing/omitted cases are reported separately, not counted as successful detections.
- [ ] Product isolation and unexpected-network rejection are demonstrated; the initial failure reaches the actual PDF input boundary.
- [ ] Review the promoted fixture diff, clean controls, field-level oracle, and representative gold pages before implementing extraction.

## T07: Select the local parsing stack from measured evidence

- [ ] Complete T07.

**Description:** Compare candidate local PDF/layout and citation parsers on a development subset, then record the selected stack and bounded installation requirements.

**Acceptance criteria:**
- [ ] Measure occurrence boundaries, title/author/year/locator extraction, diagnostic quality, resource use, and macOS/Linux installation; reserve unseen template/layout combinations for later acceptance.
- [ ] Record the selected dependencies/versions, license/packaging compatibility, and measured default limits. A separate runtime service, cloud fallback, or copied source metadata is disallowed.
- [ ] Update dependency declarations/lock only for the chosen stack; if candidates miss the contract, report the measured gap rather than weaken gold annotations.

**Verification:** Evaluate the reviewed development PDFs against T04 gold; install the selected dependency set in disposable macOS/Linux-compatible build environments; record reproducible probe commands and results in the decision note. Temporary probes/output remain ignored.

**Dependencies:** T04, T06. **Estimated scope:** M, up to five files.
**Files likely touched:** `root:tasks/pdf-parser-decision.md`, `root:pyproject.toml`, `pyproject.toml`, `uv.lock`, `tests/test_pdf_dependencies.py`.

## T08: Define the PDF evidence/report boundary

- [ ] Complete T08.

**Description:** Add typed PDF provenance, extraction diagnostics, schema-4 validation, and PDF-aware identity while retaining legacy report behavior.

**Acceptance criteria:**
- [ ] Validate document hash, parser/settings identity, ordered reference fragments, field mappings, one-based physical pages, finite coordinate bounds, diagnostics, and extraction state.
- [ ] Reject malformed JSON types and missing/invalid PDF evidence; existing schema-2/3 reports and BibTeX fingerprints retain their documented behavior.
- [ ] PDF workspace identity changes for different bytes/settings/parser versions even when normalized entries are identical; named evidence artifacts require checksums.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_schema.py tests/test_audit.py tests/test_diagnostic_schema.py`; include containers/booleans/nulls, nonfinite numbers, out-of-range pages, stale hashes, and legacy compatibility.

**Dependencies:** T04; coordinate with T07's versioned parser contract. **Estimated scope:** M, three files.
**Files likely touched:** `src/bib_lint/pdf_input/models.py`, `src/bib_lint/scope.py`, `tests/test_pdf_schema.py`.

## T09: Deliver the first compiled-PDF CLI slice

- [ ] Complete T09.

**Description:** Make one supported clean reference and one visible metadata corruption pass through actual local extraction, the public CLI, real providers with controlled HTTP, and persisted reporting.

**Acceptance criteria:**
- [ ] Select pilot cases with independently verified sufficient printed metadata; clean and corrupted results match their exact reviewed expectations.
- [ ] Preserve original text/page provenance and unknown fields; unresolved extraction already prevents Correct in this first slice.
- [ ] The CLI writes a valid schema-4 report and extraction summary, preserves PDF bytes, and makes zero network requests during extraction.

**Verification:** `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix pilot`; demonstrate red→green for the two cases, then run related schema and existing audit/CLI regressions.

**Dependencies:** T06, T07, T08. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/pdf_input/__init__.py`, `src/bib_lint/audit.py`, `src/bib_lint/verification/__init__.py`, `tests/test_pdf_e2e.py`.

## C3: Local-parser/first-slice checkpoint

- [ ] Review the chosen dependencies, install footprint, measured resource defaults, and held-out template split.
- [ ] One clean and one visibly corrupted compiled-paper case are green through the actual CLI, with the intended field-level distinction.
- [ ] Schema-2/3 and existing BibTeX behavior remain green; no parser service or TeX requirement has entered runtime.

## T10: Handle column and page transitions

- [ ] Complete T10.

**Description:** Expand the working pipeline to native two-column templates and reference continuations without assuming references are the last pages.

**Acceptance criteria:**
- [ ] Preserve reading order across columns/pages and join wrapped occurrences without merges, splits, omissions, or duplicates.
- [ ] Exclude body text, repeated headers/footers, page numbers, and subsequent appendix content; evidence retains ordered physical fragments.
- [ ] Add named real-template layout variants and fail the specific boundary/order assertion before fixing each family.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_layout.py`; `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix stress -k layout`; visually review boundary pages after fixture builds change.

**Dependencies:** T09. **Estimated scope:** M, five files.
**Files likely touched:** `src/bib_lint/pdf_input/{layout.py,segments.py,__init__.py}`, `tests/test_pdf_layout.py`, `tests/fixtures/pdf/layouts.json`.

## T11: Preserve names and text presentation

- [ ] Complete T11.

**Description:** Cover printed author structure and text transformations without inventing information lost by a bibliography style.

**Acceptance criteria:**
- [ ] Handle accents, ligatures, Unicode normalization, initials, suffixes, corporate names, and author truncation while retaining original fragments.
- [ ] Distinguish a printing abbreviation from an identity discrepancy; lost given-name information remains uncertain rather than supplied from source truth.
- [ ] Benign presentation pairs preserve semantic findings, while observable author mutations produce their specific expected findings.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_metadata.py -k 'author or unicode or text'`; `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix baseline -k author`; include clean-control outcomes.

**Dependencies:** T10. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/pdf_input/{metadata.py,__init__.py}`, `tests/test_pdf_metadata.py`, `tests/test_pdf_e2e.py`.

## T12: Preserve printed and annotated locators

- [ ] Complete T12.

**Description:** Feed all observable scholarly locators into the existing consistency checks, including relevant PDF URI annotations.

**Acceptance criteria:**
- [ ] Preserve DOI, arXiv version pins, secondary provider IDs, long wrapped URLs, real versus layout hyphens, and percent-encoded characters with field provenance.
- [ ] Retain printed/annotation disagreements and multiple supplied locators; extraction neither fetches annotation targets nor lets a correct preferred ID erase a conflicting one.
- [ ] Per-template partial/omitted expectations stay fixed; visible conflicts trigger their intended checks, while benign equivalent forms keep their expected outcomes.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_metadata.py -k locator`; `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix baseline -k locator`; run existing locator invariants.

**Dependencies:** T10, T11. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/pdf_input/{metadata.py,annotations.py}`, `tests/test_pdf_metadata.py`, `tests/test_pdf_e2e.py`.

## C4: Extraction-family checkpoint

- [ ] Supported layout, name/text, and locator cases pass their exact expectations with original spans intact.
- [ ] No occurrence disappears, duplicates, or merges; printed/annotation evidence is distinguished and never fetched during extraction.
- [ ] Clean controls and style-loss classifications remain unchanged; fixes have not turned all outcomes into Needs review.

## T13: Enforce extraction-aware decision precedence

- [ ] Complete T13.

**Description:** Expand the first slice's uncertainty guard into systematic author/field/source/coverage decision tests across the real verification path.

**Acceptance criteria:**
- [ ] Identity/boundary/compared-field extraction uncertainty blocks Correct; independently reliable mismatches can remain Invalid.
- [ ] Missing fields, partial authors, conflicting primaries, source outages, incomplete verification, and document coverage combine according to explicit expected precedence.
- [ ] Generic uncertainty, wrong-source selection, or an unrelated warning cannot satisfy a case's required finding; legacy direct-BibTeX decisions remain unchanged.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_decisions.py tests/test_status_interactions.py`; `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix baseline -k decision`.

**Dependencies:** T09, T11, T12. **Estimated scope:** M, five files.
**Files likely touched:** `src/bib_lint/verification/{matching.py,consensus.py}`, `src/bib_lint/status.py`, `tests/test_pdf_decisions.py`, `tests/test_pdf_e2e.py`.

## T14: Diagnose unsupported and bounded inputs

- [ ] Complete T14.

**Description:** Return explicit PDF extraction failures/coverage diagnostics for unreadable or unsupported inputs while applying the measured resource policy.

**Acceptance criteria:**
- [ ] Cover corrupt/empty/wrong-format/encrypted PDFs, missing or ambiguous bibliographies, image-only or mixed reference pages, unreadable text, and all agreed resource-limit boundaries.
- [ ] A scanned figure outside the bibliography does not fail a readable paper; an unreadable reference page cannot disappear from coverage or become an empty-success audit.
- [ ] Fatal extraction failures make no scholarly requests and preserve source/prior workspace bytes; reference URI actions and embedded payloads are never executed.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_inputs.py`; `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix stress -k unsupported`; test limits immediately below/at/above thresholds.

**Dependencies:** T07, T09, T10, T13. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/pdf_input/{__init__.py,limits.py}`, `tests/test_pdf_inputs.py`, `tests/pdf_e2e/negative_inputs.py`.

## T15: Resume PDF audits without stale extraction

- [ ] Complete T15.

**Description:** Exercise interruption, ownership, evidence integrity, and selective refresh through persisted PDF reports.

**Acceptance criteria:**
- [ ] Unchanged PDF/settings/parser reuse extraction and saved outcomes; refresh redoes selected source lookups without re-extracting.
- [ ] Changed bytes with identical entries, changed settings/parser, tampered evidence, or incompatible reports never silently reuse old verdicts or replace a valid workspace.
- [ ] Interruptions during extraction, writes, or verification recover as specified; source/output symlink/hardlink aliases cannot overwrite inputs.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_resume.py tests/test_resume.py`; `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix pilot -k resume`; compare original/evidence hashes before and after.

**Dependencies:** T08, T09, T13, T14. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/{audit.py,scope.py}`, `src/bib_lint/verification/__init__.py`, `tests/test_pdf_resume.py`.

## C5: Decision/recovery checkpoint

- [ ] Uncertain extraction and unavailable sources cannot create false Correct or fabricated Invalid results.
- [ ] Unsupported inputs and limit boundaries have controlled outcomes; source and prior report bytes remain intact.
- [ ] Resume/refresh semantics and stale-version rejection pass alongside legacy regression tests.

## T16: Complete CLI and installed-package contracts

- [ ] Complete T16.

**Description:** Finish public PDF options/help, machine-readable summaries, and both installed distribution paths.

**Acceptance criteria:**
- [ ] Handle `.PDF`, paths with spaces, deterministic generated keys, selected-key refresh, and default output directories; reject PDF-incompatible BibTeX flags before output replacement.
- [ ] JSON stdout remains a single final envelope; extraction coverage is separate from verification completion, with structured failures and diagnostics.
- [ ] Standalone/shared installed entry points exercise PDF extraction without checkout imports, TeX, template assets, or a parser service; existing BibTeX package contracts pass.

**Verification:** `uv run --group dev pytest -q tests/test_cli.py tests/test_package.py`; from root run the documented `tools/sciskill/tests` unittest discovery; use the test-only transport bootstrap for installed reference verification.

**Dependencies:** T14, T15. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/cli.py`, `tests/test_cli.py`, `tests/test_package.py`, `root:tools/sciskill/tests/test_package.py`.

## T17: Expose PDF evidence through viewer APIs

- [ ] Complete T17.

**Description:** Carry PDF inputs, extraction coverage, raw reference evidence, and physical page provenance through viewer session/job/presentation APIs.

**Acceptance criteria:**
- [ ] Parse only stays offline; Verify/Resume/Refresh use the same PDF audit semantics and generated keys as CLI.
- [ ] Overview/detail data distinguish coverage, metadata interpretation, and scholarly verification; display original fragments and URI targets separately.
- [ ] Valid schema-4 reports reload; malformed or missing evidence receives a controlled diagnostic rather than a misleading empty view.

**Verification:** `uv run --group dev pytest -q tests/test_pdf_viewer.py tests/test_jobs.py tests/test_viewer.py`; compare API data to the persisted CLI report for the same PDF.

**Dependencies:** T15, T16. **Estimated scope:** M, five files.
**Files likely touched:** `src/bib_lint/viewer/{app.py,jobs.py,presentation.py,data.py}`, `tests/test_pdf_viewer.py`.

## T18: Show PDF provenance in the browser

- [ ] Complete T18.

**Description:** Update the existing UI to accept PDFs and let a reader inspect extraction evidence beside verification findings.

**Acceptance criteria:**
- [ ] Setup labels/help accept PDF input and clarify unavailable AUX/encoding behavior; coverage warnings remain prominent even when verification is complete.
- [ ] Reference details expose original text, physical page numbers, extraction issues, and relevant URI evidence; untrusted content renders as inert text/validated links.
- [ ] Parse/verify/stop/resume/selected refresh work through a real browser without console errors; keyboard navigation and existing BibTeX views remain usable.

**Verification:** `uv run --group dev pytest -q tests/test_ui.py tests/test_pdf_viewer.py`; inspect the actual browser flow using compiled pilot/stress PDFs and record runtime evidence as ignored artifacts.

**Dependencies:** T17. **Estimated scope:** M, four files.
**Files likely touched:** `src/bib_lint/viewer/static/{index.html,app.js,styles.css}`, `tests/test_ui.py`.

## C6: User-flow checkpoint

- [ ] Installed CLI and viewer report the same occurrences, issue reasons, and physical page evidence.
- [ ] Extraction coverage and verification completion are visibly separate; a completed run cannot hide unreadable bibliography pages.
- [ ] PDF workflows and existing BibTeX/package/browser regressions pass.

## T19: Close the full conference/case matrix

- [ ] Complete T19.

**Description:** Run every baseline venue/corpus combination and the selected stress modes, including parser-selection holdouts and paired mutation checks.

**Acceptance criteria:**
- [ ] Every baseline build/case is accounted for; every required observable mutation yields its intended field-level finding, and supported controls meet their exact outcomes.
- [ ] No missing/extra/merged/split occurrence or incorrect provenance is accepted; partial/omitted/build-negative cases retain the pre-reviewed classifications.
- [ ] Presentation-equivalent PDFs preserve semantic outcomes; visible corruptions change the intended finding. New bugs get red E2E and focused reproductions before fixes.

**Verification:** Run `--compile --matrix baseline`, `uv run --group dev pytest -q -m pdf_e2e --pdf-matrix baseline`, and the stress matrix. Report per-template detection, clean-control, occurrence, provenance, omission, and build-failure counts separately; no aggregate percentage can conceal missing cells.

**Dependencies:** T10–T18. **Estimated scope:** M, up to five files per failure-family fix.
**Files likely touched:** `tests/test_pdf_e2e.py`, `tests/pdf_e2e/oracles.py`, `tests/fixtures/pdf/layouts.json`, plus the affected venue batch's visibility/gold files (five files total per review batch). Product fixes requiring additional files become separately sized TDD tasks; gold changes require independent review.

## T20: Gate the compiled-PDF matrix in CI

- [ ] Complete T20.

**Description:** Automate the real LaTeX-to-PDF acceptance gate while keeping the default development suite fast and offline.

**Acceptance criteria:**
- [ ] Add PR fast/package/PDF E2E jobs with pinned TeX/template assets, verified caches, all baseline configurations, named stress cases, and bounded failure artifacts; reuse the checks for release validation.
- [ ] Missing compiler/assets, compilation failures, unexpected network, failed cases, and unaccounted matrix cells fail the job; no optional-skip escape hides required coverage.
- [ ] Preserve release-time installed-package checks; document the explicit fast-test marker expression, matrix commands, and status names a maintainer can make mandatory through branch protection. Runtime package dependencies remain independent of TeX.

**Verification:** Exercise the workflow on the branch; demonstrate that a wrong expected finding, bad template checksum, and removed compiler each fail their intended gate. Reuse PDFs only when recipe hashes match; rerun product assertions on every product change.

**Dependencies:** T03, T06, T16, T19. **Estimated scope:** M, five files.
**Files likely touched:** `root:.github/workflows/pdf-e2e.yml`, `root:.github/workflows/publish.yml`, `tests/conftest.py`, `pyproject.toml`, `root:CONTRIBUTING.md`.

## T21: Document and verify the completed feature

- [ ] Complete T21.

**Description:** Publish the supported input/coverage contract in repository documentation and complete the existing distribution/quality checks for review.

**Acceptance criteria:**
- [ ] Explain local PDF extraction, supported templates/layouts, OCR limitations, generated keys, provenance, coverage versus verification, and resume/refresh behavior with actual commands.
- [ ] Document reproducible E2E setup, the 36-build baseline, required/omitted classifications, and test artifact locations without restoring development output to the diff.
- [ ] All approved success criteria and standing Definition of Done checks pass; no merge, release, or new PR is performed without the user's instruction.

**Verification:** Run fast regressions, the full baseline/stress E2E matrices, standalone/shared package checks, Ruff lint/format/complexity, Git whitespace checks, and both root/tool `uv build`; inspect the final source/artifact diff and real viewer. Summarize actual skips and remaining limitations.

**Dependencies:** T19, T20. **Estimated scope:** M, four documentation files.
**Files likely touched:** `root:README.md`, `README.md`, `root:skills/sciskill/references/bib-lint.md`, `root:SPEC-pdf-reference-input.md`.

## C7: Completion/review checkpoint

- [ ] Every approved visible issue is caught for its intended reason, clean controls meet their expected outcomes, and all matrix cells are accounted for.
- [ ] Full E2E, direct-BibTeX regressions, package, browser, build, lint, formatting, and complexity gates pass with actual results recorded.
- [ ] Public changes contain reproducible source/test/documentation files; generated PDFs, logs, audit evidence, local research workspaces, and `.agents/` remain ignored.
- [ ] The implementation matches the reviewed spec/plan, known rendering limitations are explicit, and the result is ready for human code review.
