# Check citation claims

The current agent performs claim extraction and scientific comparison. Python
extracts references, preserves source evidence, and checks the agent-written YAML.
Do not launch Codex, another model CLI, or an SDK to perform the semantic work.

## 1. Extract references and seed YAML

Identify the manuscript and optional LaTeX bibliography from the user or project
configuration. Resolve configured paths relative to the project root. If the chosen
output already contains a report, compare its private input paths with the requested
manuscript/bibliographies and run the YAML check below. Resume matching, unchanged
workspaces without reseeding or discarding claims, cached PDFs or assessments.
For changed inputs or a different manuscript, seed a new workspace and preserve
the old one. Otherwise run:

```sh
uvx sciskill bib-lint check-claims main.tex --bib references.bib --output paper-claims --json
# Or, for a PDF manuscript:
uvx sciskill bib-lint check-claims paper.pdf --output paper-claims --json
```

This reuses bib-lint's bibliography parsers and produces `claims.yaml`, with one
`citation_key` and an empty `claims` list per reference. `awaiting_agent` is the
expected result; it does not mean claims have been extracted or checked.

Read the `references` mapping in `.provenance/provenance.yaml` for titles, authors,
identifiers, URLs and PDF printed labels. From `sources`, select only `file`,
`kind` and `text_snapshot` to locate manuscript text. Use a structured YAML reader
to select these fields; do not dump the large geometry records into context.
Use these existing reference identities; do not infer original BibTeX keys from
a PDF. Do not edit captured input metadata or snapshots.

## 2. Fill the claims

Read the manuscript, including appendices and readable captions/footnotes. For
each reference, add all claims attributed to it. Uncited references keep `claims: []`.
Use the smallest complete contiguous span that retains the subject, qualifiers,
negation, comparisons and numerical conditions. Preserve the snapshot text exactly,
including line breaks and TeX commands inside the span. Do not paraphrase.
Split independently checkable assertions where contiguous spans permit it; do not
expand a quotation to an entire paragraph just because the citation ends it.

Preserve the five-field header: `schema_version`, `scikill_version`, `document`,
`setup`, and `citations`. Each citation has only `citation_key` and `claims`.
Each claim has only `claim_id`, `claim`, `location`, and `validation`:

- PDF: `location: {page: N}` uses the one-based physical page where the quote starts.
- LaTeX: `location` contains `file`, `start: {line, column}`, and `end: {line, column}`.
  Positions are one-based, Unicode columns, with the end exclusive.
- Use a unique ID per manuscript occurrence; reuse it when the same occurrence
  links to several references. Keep repeated occurrences distinct.
- Initially set `validation.result: unresolved` with a short explanation that the
  cited paper has not yet been compared. Normal `setup.validation_mode` is `agent`.

Keep attribution uncertainty explicit. A citation group can support a claim
collectively; it does not establish that every member independently supports it.
Record missing citation identities or coverage gaps in `review-notes.md`, without
inventing new public YAML fields or removing extracted references.
Inspect automated extraction diagnostics, including image-only pages. Preserve
those diagnostics; record what you inspected and any remaining gaps in the review
note. Automated warnings do not track the agent's subsequent visual review.
Derive numerical coverage counts from source-aware inspection. For automated
LaTeX tallies, reuse bib-lint's TeX lexer rather than a generic comment regex:
escaped `\%` is manuscript text, not the start of a comment.
For a PDF sentence crossing a page boundary, the contiguous captured span may
include a footer or footnote. Prefer a smaller complete claim when possible;
otherwise preserve the exact span and flag the layout text in `review-notes.md`.

## 3. Check manuscript quotations programmatically

```sh
uvx sciskill bib-lint check-claims paper-claims/claims.yaml --json
```

The same action now checks the filled YAML against freshly read original inputs.
For PDF input, each quote must exist verbatim and start on its stated page. For
LaTeX, the file/line/column slice must reproduce it exactly. Extra fields, missing
references, duplicate keys, malformed results, changed inputs and invented text
are errors. Correct the claims or locations; never rewrite input evidence to make
a quote pass. The checker preserves the agent's YAML and scientific assessments.
Successful JSON reports `status: quotes_checked`; this establishes manuscript
quotation fidelity only. It never reports scientific completion.

If the user requested extraction only, stop after this check and report that
scientific support remains unreviewed. Otherwise continue with cited PDFs.

## 4. Obtain the cited PDFs

For each reference with claims, use the original bibliographic identity to find
the corresponding full-text PDF. Reuse an already available local PDF; otherwise
use the environment's authorized retrieval tools. Existing `check-references`
results can supply verified provider records and links. Confirm title, authors,
identifiers and version before treating a PDF as the cited work.
For an unversioned arXiv URL, check its revision history against the citation's
dates; a later revision must not silently replace the cited version.

Cache each PDF once under `.provenance/reference-pdfs/`, using filesystem-safe
names. Record citation keys, local paths and retrieval URLs in the private
`.provenance/reference-pdfs.yaml` file so every assessment can be revisited.
Do not add these technical records to `claims.yaml`.

If a matching readable PDF cannot be obtained, retain `unresolved` and explain why.
Do not treat lack of access as evidence that a claim is invalid.

## 5. Compare and update the YAML

Read each cited PDF and compare its findings with the manuscript's associated
claims. Numerical claims require the actual metric, value, dataset, method and
experimental conditions to match. Examine tables/figures and limitations when
needed. Judge whether this source supports the manuscript's wording, not whether
the claim is universally true.
Assess the assertion attributed to this reference. A quoted sentence may also
describe another cited work or the manuscript's own contribution; this source need
not establish those parts. State the attributed scope in `details` when a complete
verbatim span contains several such assertions. If that scope is ambiguous, use
`unresolved`. Exact numerical matching applies to quantities attributed to the
cited work; general methodological guidance need not prescribe the current
manuscript's particular implementation choices.

Update only each claim's `validation`:

- `valid`: the cited work supports the claim as written.
- `invalid`: the cited evidence demonstrates a contradiction or overstatement.
- `unresolved`: evidence, access or attribution is insufficient to decide.

In `details`, explain the finding and identify the cited PDF and page. Include
short verbatim supporting/contradicting text or precise table/figure evidence.
Manuscript claims may paraphrase their sources; they do not need to appear
verbatim in the cited paper. The earlier verbatim check concerns the manuscript.

Run the YAML check again after edits. Report the actual completion state,
unresolved cases and coverage limits, and show `claims.yaml` and `summary.md`.
Include any review note with the report; regenerating the summary does not preserve
manual additions to it. Write `review-notes.md` before the final check so the
generated summary links it.
A passing programmatic check establishes quote/schema fidelity, not scientific
support or that every claim was found.

`--mode stub` remains an explicit testing mode. It returns `valid` with details
`Stub mode.`; it does not perform the agent's comparison or establish support.
