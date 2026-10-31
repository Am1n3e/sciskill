# PDF audit acceptance fixtures

These inputs support the planned real LaTeX → PDF → reference extraction → metadata audit tests. The production PDF adapter is not implemented yet. The test harness validates inputs, prepares official assets, and generates native-style projects; compiles them in an offline pinned container. Initial matrix execution has 20 compiled projects and 16 failures requiring review; PDF extraction tests are not implemented.

## Frozen inputs and independent truth

`corpora/manifest.json` records the exact byte hashes, entry order, types, and counts of the three earlier bibliography inputs:

| File | Entries | Role |
| --- | --- | --- |
| `corpora/representative-20.bib` | 20 | User-derived research references, plus the official Stable-Baselines3 JMLR citation; includes intentional coverage gaps |
| `corpora/rule-variants.bib` | 31 | Independently designed rule and formatting cases |
| `corpora/adversarial.bib` | 35 | Tricky author, locator, version, consistency, and source-only workflow cases |

`truth.json` contains 86 case designs and 24 source-linked metadata records. Ten additional source records were checked directly against checksum-verified archived primary metadata. Author structure was reviewed against source names or explicit source BibTeX; it was not copied blindly from normalized audit output. For example, ACL's display alias `Sujian Li (李素建)` and explicit `Li, Sujian` BibTeX identify the same author.

Canonical metadata contains facts only, not audit verdicts or comparison results. Earlier hand-specified direct-BibTeX expectations remain under `source_expectation`. The representative collection records coverage intent rather than frozen live-service outcomes. Four references have no curated primary fixture: the Nature article, book, blog, and institutional standard. This is explicit missing source coverage, not evidence that those references are invalid.

All `pdf_expectation` values are deliberately null. T04 must inspect each compiled rendering before setting a PDF-specific expectation. A source-level Correct or Invalid label is not automatically a PDF verdict. Five cases retain citation-key/AUX/cache checks that remain direct-input tests; their reference occurrences still need PDF extraction coverage.

The three BibTeX inputs are unchanged, including literal keys and original comments. References in those old comments to the former development case files are historical pointers, not required inputs here. Use the new manifest/truth files as the fixture index. If compilation needs TeX-safe build keys, preserve the originals and record a separate reversible mapping without changing citation metadata.

## Official template pins

`templates.json` describes the 12 required venue configurations and native bibliography setup. Nine downloaded official archives/repository snapshots have verified archive and selected-member SHA-256 values, covering 12 configurations:

- NeurIPS 2026, ICML 2026, ICLR 2027, AAAI 2026, IJCAI 2027, and AISTATS 2026 author kits.
- ACL, EMNLP, and NAACL configurations from one commit-pinned official ACL style-family snapshot. No conference-year release is inferred for that snapshot.
- CVPR and ICCV configurations from the commit-pinned shared official kit, using its documented conference-name/year macros; that snapshot identifies its style as CVPR 2027.
- ECCV 2026 from the repository linked by its official author guidance.

UAI is deferred by explicit user instruction because its official archive could not be retrieved. It is outside the required baseline. All 12 in-scope configurations are pinned; none may be silently omitted from the 36-build baseline.

The source links, exact revisions, archive hashes, file hashes, and baseline modes are recorded in the manifest. Downloaded author kits stay under repository-root `.local/pdf-e2e/assets/`; preserve their original notices in local projects. No vendor archive, compiled PDF, capture tree, or generated build output is committed here.

### Bibliography styles are not interchangeable

AAAI and ACL select their `.bst` automatically; the generator must not issue a second `bibliographystyle` command. AAAI also rejects `hyperref`, so a generic shared preamble would be wrong.

The NeurIPS example writes references manually and permits a consistent citation style. This benchmark explicitly chooses the standard `plainnat` style; it is not a bundled NeurIPS-specific `.bst`. The AISTATS example explicitly suggests standard `apalike` for BibTeX, which is the recorded benchmark choice. These two standard styles are tied to the immutable TeX image, not fetched independently from a changing package mirror. The remaining verified kits supply the named styles recorded in their configurations.

## Test-only compiler pin

The manifest pins the Linux/amd64 TeX Live container by immutable platform digest and records the pdfLaTeX/BibTeX pass sequence. The image was pulled and executed: pdfTeX 1.40.29 and BibTeX 0.99e from TeX Live 2026. The standard bibliography files were found and hashed. Initial compilation exercised all required template families; the matrix still contains deliberate-input build failures requiring review.

The local Docker engine is available. The pinned image supports the standard Linux/amd64 CI runner; an ARM development machine would need compatible emulation. Neither Docker nor TeX becomes a dependency of the installed PDF audit tool.

## Artifact and update policy

- Keep generated projects, PDFs, compiler logs, rendering previews, and audit outputs in ignored repository-root `.local/pdf-e2e/` or bounded CI artifacts.
- Pin official assets by content and reject checksum drift. Do not silently fetch a newer release, substitute a mirror's altered style, or omit an unavailable venue.
- Treat template or bibliography changes as fixture changes requiring new rendering review. Preserve case intent instead of changing expected answers to fit product output.
- Classify source-case evidence as printed text, URI annotation only, partial, omitted, or unable to compile before assessing the extractor. Do not count omitted information or build failures as successful PDF detections.

See repository-root `tasks/plan.md` and `tasks/todo.md` for the staged implementation and verification commands. `PYTHONPATH=src:tests python -m pdf_e2e.build --check-inputs` validates the frozen inputs and required pins from `tools/bib-lint`. `--prepare-assets` fetches or verifies the pinned archives and stages selected members under `.local/pdf-e2e/assets/`. `--compile --matrix baseline` builds every required project without network access. Missing assets, compiler errors, unresolved citations, and missing/duplicate bibliography occurrences fail the command. Per-project recipes/receipts and the complete `baseline.json` ledger stay under `.local/pdf-e2e/projects/`; failures are never counted as PDF audit detections.
