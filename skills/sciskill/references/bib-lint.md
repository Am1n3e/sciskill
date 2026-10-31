# Check bibliography references

Audit bibliography metadata against scholarly sources and show findings with their evidence. Inputs can be a BibTeX bibliography or a research-paper PDF whose reference list should be extracted. The tool never edits input PDFs, bibliographies, or compiled AUX files.

## 1. Identify the inputs

Use the PDF or bibliography supplied by the user. For a bibliography, the `bib` path in `.sciskill/config.yaml` can provide the default, resolved relative to the project root. A PDF request means auditing its reference list, not the PDF paper's own citation metadata. Ask if the path is missing or ambiguous. Use an existing compiled AUX file corresponding to the paper when checking only cited references; otherwise check all entries and state that citation usage is unknown.

For PDF input, use a local text-based PDF. OCR is deferred; unreadable bibliography regions require a readable PDF or explicit coverage review. PDF usage is unknown, and all extracted occurrences are eligible. Do not pass `--aux`, `--encoding`, or `--include-source` for PDF input.

**Output:** the input path, optional BibTeX AUX path, and scope: cited references or all entries/occurrences.

## 2. Run the audit

From the project root, run:

```sh
uvx sciskill bib-lint verify references.bib --output .sciskill/cache/bib-lint --json
```

Substitute the actual input path, including `paper.pdf` or a quoted path containing spaces. `.PDF` is accepted. Add `--aux paper.aux` only for BibTeX input when the corresponding AUX is available. Use an existing audit directory if the user is continuing a run. Repeating the same command resumes unfinished lookups and preserves saved outcomes, including failures. To retry a failed lookup, use `--refresh`; add `--key CITATION-KEY` to recheck only that reference. If an archive needs a venue, volume, or direct paper URL, report that missing context rather than repeatedly running the same broad search.

Read the final JSON result's `status`, `complete`, `scope`, `warnings`, and artifact paths. For PDFs, also read `extraction.state`, its diagnostics, occurrence count, unresolved-fragment count, and physical reference pages. `complete` describes verification work; it does not certify complete PDF coverage. A run with extraction `needs_review` must retain that qualification even when all extracted references have finished source lookups. A successful process exit can still describe a partial audit. On interruption or failure, report the saved checkpoint and unresolved work rather than claiming the audit is complete.

PDF occurrence keys such as `pdf-ref-0007` are generated in reading order and are separate from printed labels or original BibTeX keys. Resume reuses extraction for unchanged PDF bytes/parser/settings. Refresh repeats source lookups only; a changed PDF or parser needs a new output directory.

**Output:** the audit directory with its report or checkpoint and cached source evidence, plus the actual completion state, PDF coverage when applicable, and scope.

## 3. Review the findings

Inspect the report's per-reference decisions and field comparisons. For PDFs, inspect original fragments, one-based physical page locations, field evidence, and extraction diagnostics. URI annotations are retained separately from printed URLs and are never fetched during extraction. Do not treat omitted source metadata or uncertain field splitting as a demonstrated error in the printed reference. Do not fill extracted input fields from retrieved canonical records before comparison. Prioritize invalid or unresolved entries, partial matches, ambiguous records, source failures, and disagreements. Check retrieved records and primary-source links before proposing corrections.

Distinguish a demonstrated metadata mismatch from an unavailable lookup. A failed search does not establish that a publication is fabricated. Account for publication versions, preprints, and formatting differences when interpreting a mismatch. The audit checks metadata, not whether the cited work supports a scientific claim. Source styles can omit locators or shorten author names; report those rendering limitations explicitly. Uncertain extraction prevents Correct, while a reliable independent mismatch can remain Invalid.

**Output:** a concise summary of checked and skipped entries, confirmed differences with citation keys and source evidence, and unresolved items with their reasons. Keep the tool's decisions distinct from the agent's interpretation. Bibliography edits remain a separate user decision.

## 4. Show the report

Open the actual audit directory:

```sh
uvx sciskill bib-lint view .sciskill/cache/bib-lint
```

Verify the user's browser shows that audit's scope, completion state, PDF coverage when applicable, and reference details. Parse only performs local extraction without scholarly requests; Verify starts the normal source-verification workflow. If an interrupted audit is shown, identify it as partial. Reload rereads saved output; rechecking sources starts new lookups.

**Output:** the report visible in the browser, with the findings and evidence ready for the user to inspect.
