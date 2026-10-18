# Check a bibliography

Audit bibliography metadata against scholarly sources and show findings with their evidence. The tool reads the bibliography and compiled AUX files without editing them.

## 1. Identify the inputs

Use the bibliography supplied by the user or the `bib` path in `.sciskill/config.yaml`, resolved relative to the project root. Ask if the path is missing or ambiguous. Use an existing compiled AUX file corresponding to the paper when checking only cited references; otherwise check all entries and state that citation usage is unknown.

**Output:** the bibliography path, optional AUX path, and agreed scope: cited references or all entries.

## 2. Run the audit

From the project root, run:

```sh
uvx sciskill bib-lint verify references.bib --output .sciskill/cache/bib-lint --json
```

Substitute the actual bibliography path. Add `--aux paper.aux` when the corresponding AUX is available. Use an existing audit directory if the user is continuing a run. Repeating the same command resumes unfinished lookups and preserves saved outcomes, including failures. To retry a failed lookup, use `--refresh`; add `--key CITATION-KEY` to recheck only that reference. If an archive needs a venue, volume, or direct paper URL, report that missing context rather than repeatedly running the same broad search.

Read the final JSON result's `status`, `complete`, `scope`, `warnings`, and artifact paths. A successful process exit can still describe a partial audit. On interruption or failure, report the saved checkpoint and unresolved work rather than claiming the audit is complete.

**Output:** the audit directory with its report or checkpoint and cached source evidence, plus the actual completion state and scope.

## 3. Review the findings

Inspect the report's per-reference decisions and field comparisons. Prioritize invalid or unresolved entries, partial matches, ambiguous records, source failures, and disagreements. Check retrieved records and primary-source links before proposing corrections.

Distinguish a demonstrated metadata mismatch from an unavailable lookup. A failed search does not establish that a publication is fabricated. Account for publication versions, preprints, and formatting differences when interpreting a mismatch. The audit checks metadata, not whether the cited work supports a scientific claim.

**Output:** a concise summary of checked and skipped entries, confirmed differences with citation keys and source evidence, and unresolved items with their reasons. Keep the tool's decisions distinct from the agent's interpretation. Bibliography edits remain a separate user decision.

## 4. Show the report

Open the actual audit directory:

```sh
uvx sciskill bib-lint view .sciskill/cache/bib-lint
```

Verify the user's browser shows that audit's scope, completion state, and reference details. If an interrupted audit is shown, identify it as partial. Reload rereads saved output; rechecking sources starts new lookups.

**Output:** the report visible in the browser, with the findings and evidence ready for the user to inspect.
