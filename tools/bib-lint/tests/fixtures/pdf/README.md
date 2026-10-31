# PDF audit acceptance fixtures

These inputs exercise the real LaTeX → PDF → reference extraction → metadata audit path. The harness validates frozen inputs, prepares official assets, generates native-style projects, and compiles them in an offline pinned container. Public CLI tests give the product only a copied PDF and control scholarly HTTP transport; extraction, provider adapters, comparisons, and consensus run for real.

## Frozen inputs and independent truth

`corpora/manifest.json` records the exact byte hashes, entry order, types, and counts of the three earlier bibliography inputs:

| File | Entries | Role |
| --- | --- | --- |
| `corpora/representative-20.bib` | 20 | User-derived research references, plus the official Stable-Baselines3 JMLR citation; includes intentional coverage gaps |
| `corpora/rule-variants.bib` | 31 | Independently designed rule and formatting cases |
| `corpora/adversarial.bib` | 35 | Tricky author, locator, version, consistency, and source-only workflow cases |

`truth.json` contains 86 case designs and 24 source-linked metadata records. Ten additional source records were checked directly against checksum-verified archived primary metadata. Author structure was reviewed against source names or explicit source BibTeX; it was not copied blindly from normalized audit output. For example, ACL's display alias `Sujian Li (李素建)` and explicit `Li, Sujian` BibTeX identify the same author.

Canonical metadata contains facts only, not audit verdicts or comparison results. Earlier hand-specified direct-BibTeX expectations remain under `source_expectation`. The representative collection records coverage intent rather than frozen live-service outcomes. Four references have no curated primary fixture: the Nature article, book, blog, and institutional standard. This is explicit missing source coverage, not evidence that those references are invalid.

The source truth's `pdf_expectation` values remain null: PDF-specific expectations live in `renderings.json` and `stress-renderings.json`, bound to exact compiled PDF hashes. They record native field visibility and author presentation rather than inheriting direct-BibTeX verdicts. Independently measured physical-page/first-line anchors verify provenance. Five cases retain citation-key/AUX/cache checks in the direct-input tests; their visible reference occurrences are still extracted from PDFs.

The three BibTeX inputs are unchanged, including literal keys and original comments. References in those old comments to the former development case files are historical pointers, not required inputs here. Use the new manifest/truth files as the fixture index. If compilation needs TeX-safe build keys, preserve the originals and record a separate reversible mapping without changing citation metadata.

## Official template pins

`templates.json` describes the 12 required venue configurations and native bibliography setup. Nine downloaded official archives/repository snapshots have verified archive and selected-member SHA-256 values, covering 12 configurations:

- NeurIPS 2026, ICML 2026, ICLR 2027, AAAI 2026, IJCAI 2027, and AISTATS 2026 author kits.
- ACL, EMNLP, and NAACL configurations from one commit-pinned official ACL style-family snapshot. No conference-year release is inferred for that snapshot.
- CVPR and ICCV configurations from the commit-pinned shared official kit, using its documented conference-name/year macros; that snapshot identifies its style as CVPR 2027.
- ECCV 2026 from the repository linked by its official author guidance.

UAI is deferred by explicit user instruction because its official archive could not be retrieved. It is outside the required baseline. All 12 in-scope configurations are pinned; none may be silently omitted from the 36-build baseline.

The source links, exact revisions, original archive hashes, file hashes, and baseline modes are recorded in the manifest. Required unmodified author-kit sources and notices are committed under `tests/assets/pdf/`. Preparation verifies every member checksum and stages copies under repository-root `.local/pdf-e2e/assets/` without downloading. No archive, compiled PDF, capture tree, or generated build output is committed here.

### Bibliography styles are not interchangeable

AAAI and ACL select their `.bst` automatically; the generator must not issue a second `bibliographystyle` command. AAAI also rejects `hyperref`, so a generic shared preamble would be wrong.

The NeurIPS example writes references manually and permits a consistent citation style. This benchmark explicitly chooses the standard `plainnat` style; it is not a bundled NeurIPS-specific `.bst`. The AISTATS example explicitly suggests standard `apalike` for BibTeX, which is the recorded benchmark choice. These two standard styles are tied to the immutable TeX image, not fetched independently from a changing package mirror. The remaining verified kits supply the named styles recorded in their configurations.

## Test-only compiler pin

The manifest pins the Linux/amd64 TeX Live container by immutable platform digest and records the pdfLaTeX/BibTeX pass sequence. The executed compiler is pdfTeX 1.40.29 and BibTeX 0.99e from TeX Live 2026. Standard bibliography files are hashed. All 36 original projects are accounted for: 20 compile and 16 fail on deliberately malformed source citations. `build_cases.json` attributes those failures through 26 isolated build-negative reproductions. Explicit renderable subsets retain the other cases; three positive counterparts preserve the ACL-family rendering checks. The acceptance inventory has 39 baseline PDFs plus six held-out native modes. A native compilation failure never counts as a detected PDF citation issue.

The local Docker engine is available. The pinned image supports the standard Linux/amd64 CI runner; an ARM development machine would need compatible emulation. Neither Docker nor TeX becomes a dependency of the installed PDF audit tool.

## Artifact and update policy

- Keep generated projects, PDFs, compiler logs, rendering previews, and audit outputs in ignored repository-root `.local/pdf-e2e/` or bounded CI artifacts.
- Pin official assets by content and reject checksum drift. Do not silently fetch a newer release, substitute a mirror's altered style, or omit an unavailable venue.
- Treat template or bibliography changes as fixture changes requiring new rendering review. Preserve case intent instead of changing expected answers to fit product output.
- Classify source-case evidence as printed text, URI annotation only, partial, omitted, or unable to compile before assessing the extractor. Do not count omitted information or build failures as successful PDF detections.

See [the PDF guide](../../../../../docs/pdf-reference-input.md) for complete reproduction commands. `PYTHONPATH=tests uv run --locked --group dev python -m pdf_e2e.build --check-inputs` validates frozen inputs and required pins from `tools/bib-lint`. `--prepare-assets` verifies the vendored files and stages them under `.local/pdf-e2e/assets/` offline. `--compile --matrix baseline` builds every required project without network access. Missing assets, unexpected compiler errors, unresolved citations, missing/duplicate bibliography occurrences, or incomplete gold fail. Per-project recipes/receipts and the `baseline.json`/`acceptance.json` ledgers stay under `.local/pdf-e2e/projects/`. Selecting `pytest -m pdf_e2e --pdf-matrix baseline` runs the required PDF-only acceptance tests; `--pdf-matrix stress` selects the six held-out modes.
