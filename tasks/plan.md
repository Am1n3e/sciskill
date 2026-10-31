# Implementation plan: PDF reference auditing through conference-paper E2E tests

Status: The user authorized gradual implementation. T01 and T02 are complete. UAI is deferred by explicit user instruction; all 12 in-scope venue configurations have verified pins and the baseline is 36 projects. Compiler tooling, PDF runtime behavior, dependencies, and CI integration remain unimplemented.

Specification: [SPEC-pdf-reference-input.md](../SPEC-pdf-reference-input.md).
Task list target: [todo.md](todo.md). Use these files as the single plan/task index; no external tracker is designated.

## Outcome and scope

Take the earlier bibliography cases, generate research-paper LaTeX projects using official conference templates, compile them, and require the PDF-input workflow to detect every issue that survives into the PDF, for the correct reason. Preserve the existing direct-BibTeX suite for checks whose input information is lost in typesetting.

The first release targets text-based papers, local extraction without a service, CLI auditing, and the existing viewer. OCR is deferred; unreadable reference pages receive explicit diagnostics. Runtime code must not depend on LaTeX, a container, or the template downloader. Those are test-build tools only.

## Test architecture

```text
Frozen bibliography inputs + canonical metadata + explicit case mutations
                         │
Pinned official template + fixed generated body text + pinned TeX build
                         │
                PDF + compile provenance
                         │
          Independent rendering/visibility annotations
                         │
          Isolated product run: PDF as its only document input
                         │
   Real extraction → parsing → provider adapters → consensus → report
                         ↑
          Deterministic scholarly HTTP response fixtures
                         │
     Assert occurrences, fields, provenance, issue codes, and statuses
```

Expected answers must not come from the extractor, matcher, current verdicts, or a direct-BibTeX audit. Canonical metadata and case intent are independently curated; per-template rendered evidence is inspected before product development. `.bbl` and `.aux` can help the harness establish rendering order, but they never enter the product run.

### Corpus and venue matrix

| Corpus | Earlier local source | Purpose |
| --- | --- | --- |
| Representative | `.local/bib-lint-development/tests/fixtures/e2e/representative-20.bib` | 20 varied reference occurrences; establish expected outcomes per rendered control, without assuming every original entry is error-free |
| Rule variants | `.local/bib-lint-development/tests/fixtures/e2e/rule-variants.bib` | 31 controlled rules and formatting cases |
| Adversarial | `.local/bib-lint-development/tests/fixtures/e2e/adversarial.bib` | 35 tricky identity, locator, author, and consistency cases |

| Stable venue IDs | Official template source to resolve and pin in T02 |
| --- | --- |
| `neurips`, `icml`, `iclr` | [NeurIPS](https://neurips.cc/Conferences/2026/CallForPapers), [ICML](https://icml.cc/Conferences/2026/AuthorInstructions), [ICLR](https://iclr.cc/Conferences/2027/AuthorGuidelines) |
| `aaai`, `ijcai` | [AAAI author kit](https://aaai.org/authorkit26-1/), [IJCAI author kit](https://www.ijcai.org/authors_kit) |
| `aistats` | [AISTATS](https://virtual.aistats.org/Conferences/2026/CallForPapers) |
| `acl`, `emnlp`, `naacl` | [ACL official style repository](https://github.com/acl-org/acl-style-files); distinct venue configurations |
| `cvpr`, `iccv`, `eccv` | [CVPR/ICCV author kit](https://github.com/cvpr-org/author-kit), [ECCV author guidance](https://eccv.ecva.net/Conferences/2026/SubmissionPolicies) |

Baseline: 12 venue configurations × 3 corpora = 36 required project builds. This is an explicit initial list, not a claim to cover every AI conference or historical template. Pin the actual year/release, asset checksums, bibliography style, engine, and default mode after inspecting the official files. Never assume a venue/year has a particular column layout from its name alone.

Add supported review/final/preprint modes and stress layouts as named cases after the baseline is established. Do not multiply every option blindly. Build every case once per content/toolchain hash and reuse the resulting PDF throughout product TDD.

### Expectations and observability

The manifest records source case ID, occurrence ID, canonical record, intended mutation, rendered order/label, physical page evidence, accepted field spans, required diagnostic, permitted status, and visibility classification.

Visibility classes are `text`, `annotation_only`, `partial`, `omitted`, and `compile_failure`. They are reviewed before extraction implementation and cannot be relabeled just because a product test fails. Partial cases specify exactly which claims remain testable. URI annotations are recorded separately from displayed text, including disagreeing targets; extraction does not fetch those links.

Printed names may lose given-name information; styles may suppress DOI/eprint/URL or one venue field; source keys and AUX use are normally absent. Keep those source-only expectations in the direct-BibTeX suite. Where useful, add a separately identified visible counterpart without modifying the official `.bst` or pretending that it is the unchanged original case.

A `compile_failure` is attributed to its source/asset and reported separately. Required supported projects must compile. An intrinsically non-renderable case needs an explicitly reviewed build-negative expectation; it is never a passing PDF detection or an unreported skip. TeX-safe build-key mapping is allowed, recorded, and must not mutate citation fields or frozen inputs.

### Isolation and controlled source responses

- Copy the compiled PDF into a fresh product working directory. Do not copy source bibliographies, `.bbl`, `.aux`, truth manifests, or case-ID mappings. Add a test-only file-access guard for those harness inputs.
- Use the real public CLI entry point and audit workspace with the real extractor, providers, matching, and consensus. A test-only bootstrap may configure the HTTP transport; do not add production bypass flags or replace the verifier with a fake provider registry.
- Provide fixed protocol-shaped source responses for existing adapters from canonical truth, never from corrupted input fields. Unexpected queries and external connections fail the test. Provider outages, conflicting records, and incomplete searches have separate explicit response scenarios.
- Assert the persisted report and final JSON as well as process status. An unrelated source failure or generic Needs review is not the expected detection.
- Separate artifact/build failures, extraction failures, metadata-parse failures, verification failures, and oracle/visibility disagreements in test output.

## Architecture decisions and unresolved choices

1. **Keep one verifier.** PDF handling adapts document evidence to the existing entry/provider boundary. Extraction confidence and unknown fields are preserved through comparison and consensus.
2. **Start with a thin CLI slice.** After the harness and dependency decision, make one clean and one visibly corrupted compiled-paper case work end to end. Expand by failure family rather than implementing an entire extractor before testing it.
3. **Local parser choice is evidence-driven.** In T07, compare in-process layout extraction and local citation-parsing candidates on a development subset. Reserve unseen template/layout combinations for acceptance. Record installation footprint, supported platforms, field accuracy, failure behavior, and resource use. A service or cloud fallback fails the requirement. If no candidate meets the contract, report the measured limitation at checkpoint C3 rather than weaken expected answers.
4. **Version PDF evidence.** Introduce PDF report schema 4 while retaining schema-2/3 readers and existing BibTeX output behavior. Validate provenance and extraction summaries at boundaries. Bump decision/orchestration versions where reuse semantics change.
5. **Content-aware ownership.** PDF bytes, extractor/parser versions, and settings identify extraction. Entry hashes alone do not protect an occupied workspace. Resume reuses unchanged extraction; `--refresh` refreshes scholarly evidence only. Parser-version changes require a new workspace in v1.
6. **Minimal reproducible public fixtures.** Promote only the three agreed bibliography inputs and necessary compact truth/response data into named test fixtures after checking contents and attribution. Do not restore the prior development tree or large captured evidence. Generated PDFs, logs, previews, checkpoints, and benchmark output go under `.local/pdf-e2e/` or CI artifacts, not Git.

## Dependency graph and task index

Detailed checklists, file budgets, progress, and verification results are in [todo.md](todo.md).

```text
T01 corpus ───────────┐
T02 template pins ────┴→ T03 compile projects → C1
                                      │
                       T04 + T04a–d rendering oracles ──┐
T01 → T05 HTTP replay ────────────────────────┴→ T06 red E2E harness → C2
                       │                                  │
                       ├→ T07 local parser decision ───────┤
                       └→ T08 schema/identity boundary ────┴→ T09 first CLI slice → C3
                                                                │
                                            T10 columns → T11 names → T12 locators → C4
                                                                                │
                                                   T13 decision gates → T14 bad inputs → T15 resume → C5
                                                                                              │
                                                           T16 CLI/package → T17 viewer API → T18 viewer UI → C6
                                                                                                               │
                                                                            T19 full matrix → T20 CI → T21 docs/release checks → C7
```

| Tasks | Review checkpoint |
| --- | --- |
| T01–T03: freeze inputs, pin assets, compile real projects | C1: assets/builds are reproducible and inputs remain unchanged |
| T04/T04a–d, T05–T06: annotate renderings in bounded batches, replay HTTP, establish meaningful red E2E tests | C2: independent expectations, no source leakage, failures attributed correctly |
| T07–T09: choose/install local parser, version evidence, complete first CLI slice | C3: review dependency decision, measured limits, and first red→green proof |
| T10–T12: expand actual layouts, names/text, and printed/annotated identifiers | C4: those issue families pass with clean controls |
| T13–T15: uncertainty decisions, unsupported PDFs, interruption/resume | C5: no false Correct, stale reuse, or damaged workspace |
| T16–T18: public options, installed-package behavior, viewer evidence | C6: CLI/viewer show matching provenance and coverage |
| T19–T21: full matrix, automated gate, documentation/distribution | C7: all agreed cases accounted for and ready for review |

## TDD execution rules

For each behavioral task: select a reviewed rendered case, assert its exact outcome, and record a failure that reaches the intended product boundary. Fix the smallest behavior, prove that case green, then run related regressions. Add a focused unit/integration reproduction for diagnosis without replacing the compiled-PDF acceptance test.

Before the first PDF feature exists, the E2E harness should reject the current CLI's unsupported `.pdf` result. After that first slice, a red author/locator/layout test must fail on its specific behavior, not on missing setup or an unrelated exception. Do not use blanket xfail, skip missing TeX in the required job, return Needs review for every case, or accept current outputs as expected answers.

Use state/output assertions. Check required field-level diagnostics, occurrence completeness, source text, page evidence, selected-record identity, and statuses. Test paired clean/corrupt PDFs and benign presentation variants. If two source variants render the same citation evidence, require equivalent semantic findings rather than impossible source-level recovery.

## Verification commands and gates

Existing commands, from `tools/bib-lint`:

```sh
uv run --group dev pytest -q -m 'not package'
uv run --group dev pytest -q tests/test_package.py
uv run --group dev ruff check .
uv run --group dev ruff format --check .
uv run --group dev ruff check . --select C901 --ignore-noqa
uv build
```

Planned commands, added by the task that owns each capability; they do not exist yet:

```sh
# Validate frozen inputs and official template pins.
PYTHONPATH=tests uv run --group dev python -m pdf_e2e.build --check-inputs

# Fetch only pinned template assets, then compile the baseline projects.
PYTHONPATH=tests uv run --group dev python -m pdf_e2e.build --prepare-assets
PYTHONPATH=tests uv run --group dev python -m pdf_e2e.build --compile --matrix baseline

# Product acceptance tests use compiled PDFs and controlled HTTP responses.
uv run --group dev pytest -q -m pdf_e2e --pdf-matrix pilot
uv run --group dev pytest -q -m pdf_e2e --pdf-matrix baseline
uv run --group dev pytest -q -m pdf_e2e --pdf-matrix stress
```

Use an importable test-harness package without changing how the existing tests import their support modules. Register `pdf_e2e` and the matrix option explicitly; heavy tests are deselected unless a PDF matrix is selected. Once selected, missing TeX/assets fail rather than skip. The fast command must stay offline and runnable without TeX; fast PDF fixtures can be generated with a lightweight test PDF library or use tiny reviewed compiled fixtures. The required E2E job must build LaTeX projects, so those fast fixtures cannot replace real compilation coverage.

After registering the heavy marker, use `uv run --group dev pytest -q -m 'not package and not pdf_e2e'` for the fast job. The repository currently has release-time package checks in `publish.yml`, not a Python PR test workflow. T20 adds fast, package, and PDF E2E jobs for PRs and reuses those checks for release validation without removing the existing installed-package tests. Making their status names mandatory for merging is a separate repository branch-protection setting; do not claim a workflow file alone configures that policy.

From the root, verify the shared launcher/package with the documented unittest command and `uv build`. Record exact TeX commands and versions from T02/T03; fail compilation on errors, unresolved bibliography entries, or missing assets. Shell escape is disabled. Asset preparation is the only networked part of corpus building; subsequent compilation and product acceptance are offline.

## Artifact policy and performance

Track manifests, generator sources, bibliography fixtures, reviewed gold annotations, compact HTTP response builders/data, and tests. Keep build directories and reports under ignored `.local/pdf-e2e/`. CI stores failures as bounded downloadable artifacts tied to template/corpus/toolchain hashes.

Cache template assets by checksum and PDFs by the complete build recipe, not by the product commit. A product change must rerun assertions even when a PDF is reused. Compare semantic extraction, not creation timestamps or incidental PDF metadata. Avoid rebasing exact-coordinate annotations onto a different PDF build without review.

Benchmark extraction on development fixtures before choosing numeric byte/page/content/text/reference/time limits. Define those defaults at C3 and test each limit boundary in T14. Include an oversized/adversarial PDF, not only normal compiler output. CI job timeouts and cache budgets are chosen from measured baseline builds, not guessed now.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Typesetting erases the intended defect | Freeze visibility per style, expose omitted counts, retain source-only tests, add separately labeled visible counterparts when appropriate |
| Test answer leaks through `.bib`, keys, hidden markers, or HTTP truth | Product input is PDF-only; file-access checks; no case IDs/expected labels embedded in generated text; canonical responses never derive from corrupted entries |
| A blanket uncertain verdict looks safe but catches nothing | Exact issue/field assertions and expected clean outcomes; unrelated warnings do not pass |
| Good results only on tuned layouts | Keep template/layout combinations held out during parser selection; run all 36 baseline builds plus named stress cases at release |
| Template URLs or dependencies drift | Version/checksum pins, cache verification, explicit reviewed template-update task |
| LaTeX error mistaken for extraction error | Separate build status, attributed case diagnostics, no quiet deletion or skip |
| PDF library parses text but not citation boundaries accurately | Fail-fast parser comparison on reviewed renderings; retain raw spans and unknown fields; no source metadata copied into input |
| Schema migration or stale extraction changes a verdict | Strict validators, legacy compatibility tests, PDF-aware fingerprints, parser/version invalidation |
| Runtime installs become dependent on compiler/service setup | Keep TeX/templates/harness in development tooling; test installed wheels in a clean environment without TeX or parser services |

## Parallel work and review policy

Once contracts are fixed, T01 and T02 can be prepared independently; T05 can run alongside T04; different template families and independent gold reviews can be assigned separately. Product tasks that share `audit.py`, `scope.py`, `matching.py`, or consensus are sequential. Viewer backend precedes frontend integration. T19 joins all required slices before CI is made a release gate.

No agents are dispatched by this planning turn. Any later parallel work must have disjoint file ownership, agreed manifest/schema contracts, and one integration owner. Independent reviewers may challenge gold labels; they cannot relabel a failing test to match the product.

## Questions and review decisions

- Confirm the explicit 12-venue list as the initial meaning of major AI conferences; add other venues through named manifest entries rather than an unbounded “all” claim.
- Review the local parser choice, installation footprint, supported dependency versions, and measured resource limits at C3.
- Review corpus promotion and all visibility exceptions at C2. Keep compiled artifacts and the earlier removed development/evidence tree out of the public diff.
- Review the PDF schema/CLI extraction-summary proposal before integrating it with product decisions. Existing schema-2/3 and BibTeX contracts remain acceptance gates.

Implementation is authorized in small verified commits. Checkpoints are concrete review points; they must not silently reduce scope, modify expectations, or introduce a service/cloud fallback. Parser choice, measured limits, and rendering exceptions remain explicit review decisions at their named checkpoints.
