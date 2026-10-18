# Plan a rebuttal

Analyze initial reviewer feedback against the submitted manuscript and appendix. Produce annotated concerns, evidence-based analysis, shared themes, and proposed tasks for the author to review.

The rebuttal manifest links these outputs. Use [the manifest template](../assets/rebuttal-manifest.yaml), replacing placeholders with actual values. Save it as `workspace.yaml` in the rebuttal folder; document paths are relative to that folder. Preserve existing drafts and author decisions when updating an analysis.

## 1. Establish the inputs

Identify the submitted manuscript, its appendix or supplement, the initial reviews, and the destination folder. Ask for missing inputs or an ambiguous manuscript version. Record the paths, hashes, versions, and source review dates in a local provenance file. Distinguish review dates from capture dates; mark unavailable information as unknown. Check modification dates and revision history: a current review post may contain rebuttal updates, and the current PDF may be camera-ready. Describe a snapshot as initial only when its pre-response version is verified.

For a saved OpenReview discussion, import it into a new rebuttal folder:

```sh
uvx sciskill rebuttal import-openreview initial-reviews.html my-rebuttal
```

Read the manuscript and all initial reviewer/editor feedback. Keep author responses, subsequent exchanges, and previous rebuttal analyses outside the analysis inputs. Preserve the original capture. Record uncertainty if the manuscript or a captured review was edited after submission.

**Output:** an identified manuscript and review set, provenance, and imported review YAML files linked from the manifest. Each review retains its ID, reviewer ID, ordered headings and content, timestamps, and source checksum. An initial-only working copy has empty conversation lists.

## 2. Annotate actionable passages

Mark every passage that needs an answer or requested change in `annotated_content`, leaving original headings and `content` intact. Use the smallest complete span that preserves the request and its qualifiers. Split independent asks; keep tightly coupled asks together and account for each part in the assessment.

Wrap each span in `science-skills-annotation` with a stable, globally unique `id` and one `type`:

- `clarification`: an explanation, justification, or answer without an explicit requested modification.
- `change_request`: a requested modification or new evidence. Set `subtype` to `manuscript_change` or `additional_experiments` when applicable; otherwise omit it.

Classify the reviewer's request, not the work the author later chooses. Preserve Markdown inside each tag and keep spans non-overlapping. Repeated substantive mentions can link to one resolution; praise, administrative text, and bare cross-references need no annotation.

**Output:** annotated review sections and matching manifest concerns with concise topic titles. Original content and checksums are unchanged. Each concern has analysis and response file paths; create empty response files for this analysis-only workflow.

## 3. Assess each concern against the paper

Write the following in each concern's analysis file:

| Item | Expected content |
| --- | --- |
| Request | What the reviewer asks, including material subquestions. |
| Underlying issue | Why the concern matters, distinguishing interpretation from the reviewer's words. |
| Resolution criterion | The evidence or explanation that would answer the concern. |
| Existing evidence | Precise manuscript section, page, table, or algorithm references and what they establish. |
| Coverage | Answered, partially answered, or unanswered by the supplied paper. |
| Remaining work | A clarification, verification, manuscript change, or proposed experiment, with its reason. |

For an existing answer, explain it and cite its location rather than merely pointing to an appendix. Check the relevant supplementary material before declaring evidence missing. Keep reported results distinct from claims or unverified implementation behavior. Preserve comparison conditions, denominators, and uncertainty; acknowledging a limitation does not supply empirical evidence. State uncertainty without inventing results or predicting acceptance.

**Output:** one evidence-grounded assessment per concern, with a resolution criterion for every material ask and explicit gaps where the paper does not answer it.

## 4. Group concerns into themes

Group concerns by the underlying issue or evidence needed to resolve them. Retain material issues raised by a single reviewer. Explain each reviewer's request within the shared analysis, including differences or conflicting expectations.

Give each theme a stable ID and number, title, Markdown content file, explicit reviewer IDs, and linked concern IDs. The viewer displays theme content; concern assessment files are working records, not separate viewer panels. Include each linked concern’s request, underlying issue, resolution criterion, paper evidence, coverage, and remaining work in its theme content, with links to the concern. Consolidate shared evidence while retaining reviewer-specific qualifications so the author can assess every finding in the Analysis tab.

**Output:** linked themes covering the assessed concerns. A theme's reviewer list contains exactly the distinct owners of its linked concerns; shared membership does not imply agreement on every point.

## 5. Propose and prioritize tasks

Create tasks for concrete deliverables and link every concern each task addresses. Combine duplicate work while preserving separate resolution criteria. Distinguish verifying existing evidence from performing new experiments.

New tasks start `proposed`; user agreement moves them to `pending`. Keep existing decisions and progress. Set priority by impact on the central claims, validity, fairness, and reproducibility; track effort separately. Explain priority and dependencies in `note`. Small wording fixes should not displace material evidence gaps.

**Output:** uniquely numbered tasks linked to concerns and themes, with status, priority, effort, note, and an external link when supplied. Response drafts and manuscript changes remain for the author's next action.

## 6. Write the overview

Update one overview Markdown file, linked from the manifest. Begin directly with the content; the viewer supplies the “Overview” heading.

Include:

- Manuscript path/version, update time, source review dates, and material version uncertainty.
- Counts of themes, reviewers, concerns, and tasks, including current task status counts using the manifest’s status values.
- All themes with reviewer counts/IDs and related task links. Sort by descending unique reviewer count, then stable theme number; use that order in the manifest without renumbering themes.
- A short “Where to start” list of concrete actions and why they matter.
- Useful answers already in the paper, with precise paper references and linked concerns or follow-up tasks.

Link substantive issues to their concerns, themes, or tasks. Keep extraction procedures and validation logs in local provenance files so the overview helps the researcher decide what to do next.

**Output:** a single overview connecting the review findings, available evidence, and proposed work.

## 7. Validate and show the result

Run:

```sh
uvx sciskill rebuttal validate my-rebuttal
```

The command checks structure, files, and links; an imported review with no concerns can pass. Separately check complete review coverage, original checksums and exact text preservation, matching annotation/concern IDs, unique task/theme numbers, existing linked files, and empty response drafts. Use the tool's checksum verification; source changes are errors, not a reason to replace the checksum. Theme numbers and task IDs in the populated template must be YAML integers.

Use these viewer links with persisted IDs: `#REVIEWER/CONCERN-ID`, `#theme-THEME-ID`, and `#task-NUMBER`. A reviewer-only link opens the full review.

If independent review is requested, have reviewers check omissions, evidence, and priorities against the allowed inputs. Reconcile supported findings and retain unresolved disagreements.

Open the viewer and refresh the user's actual browser tab:

```sh
uvx sciskill rebuttal view my-rebuttal
```

**Output:** a validated rebuttal manifest with the overview, themes, annotations, tasks, and links verified in the browser. Report unresolved evidence gaps to the author.
