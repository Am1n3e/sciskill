# Plan a rebuttal

Turn initial reviews and the manuscript into an evidence-grounded response plan. Read the [workspace contract](workspace.md) before writing workspace data. Use the Rebuttal Desk importer and validator through UVX.

The manuscript and its available appendix or supplement are required. Preserve existing human decisions and drafts on reruns. Do not generate response drafts, run experiments, modify the manuscript, or mark tasks accepted or done unless requested. Distinguish the reviewer's stated request from your interpretation; describe evidence that would resolve it rather than predicting the reviewer's vote.

## Establish the inputs

Record manuscript path/version/hash, source review paths/hashes, extraction tool, and review scope. Read the complete manuscript and appendix relevant to the claims, plus all initial reviews. Use the initial version of the paper when available. A later PDF can be examined only with its provenance stated; answers found there are not automatically evidence of what the reviewer received. Use only initial review entries: exclude author responses, later exchanges, decisions informed by them, and prior rebuttal analyses. Record uncertainty if a captured initial review was subsequently edited.

Import a complete saved OpenReview HTML with `rebuttal-desk import-openreview`. For isolated initial-review fragments, assemble only the selected original review elements under the importer containers; retain the originals and log the assembly. Create a new workspace for a fresh analysis instead of overwriting an existing rebuttal. Keep personal captures and generated analysis in the repository's ignored workspace area.

## Understand and annotate

Read every substantive field, including weaknesses, questions, and limitations. Mark the smallest complete passage that expresses an independently answerable issue. Include necessary qualifiers; do not annotate praise, administrative acknowledgements, or a repeated 'see above' pointer. Repeated substantive mentions may have separate span IDs linked to one resolution so none of the original text disappears. Record why unannotated passages need no action.

Use one main type per span:
- `clarification`: explain, justify, or answer a criticism/question without an explicit requested modification.
- `change_request`: a requested modification or new evidence. Optional subtype: `manuscript_change` or `additional_experiments`. Leave it unset when neither fits.

The type reflects what the reviewer asks, not the work the author later chooses. A clarification can lead to a proposed manuscript edit. An explicit request for measurement is a change request even when phrased as a question. When a passage combines tightly coupled asks, retain the full span and enumerate its distinct obligations in its analysis. Split independent asks when their evidence or completion criteria differ. IDs are stable; titles are short topics, not copied questions.

## Build an evidence-grounded assessment

For every concern, record in its analysis:
- **What is asked:** explicit questions/assertions, including every material subquestion.
- **Underlying issue:** the interpretation and why it matters; label uncertainty instead of mind-reading.
- **What would resolve it:** observable evidence or explanation that addresses this concern. Distinguish the requested evidence from a sufficient narrower response that admits a limitation.
- **Manuscript evidence:** precise section/page/table/algorithm/line references, a short supporting excerpt when useful, and what the passage actually establishes.
- **Coverage:** answered, partially answered, or not answered by the provided manuscript. 'Acknowledged as a limitation' is not 'empirically answered'. Separate reported evidence from claims, formal descriptions, and unverified implementation behavior.
- **Remaining work:** clarify using existing evidence, verify an implementation/log fact, propose a manuscript change, or propose additional measurement/experiments. Do not invent results or assume a hypothetical control exists.

For already answerable questions, explain the answer and cite the location; do not merely say 'see Appendix'. A reviewer may have identified unclear presentation even when the fact exists. When quoting comparative results, retain relevant denominators, conditioning populations, native update paths and uncertainty; a shared headline metric need not mean a matched comparison. For claimed absences, inspect relevant appendices/tables before declaring evidence missing. For concerns about budget, leakage, safety, or causality, check the exact boundary of the existing measurement.

## Synthesize across reviewers

Group by shared underlying issue or shared resolving evidence, not shared keywords. Link each theme to exact concern IDs and explicit reviewer IDs. A one-reviewer material issue still deserves a theme. State which reviewer asks what and where their needs differ; shared membership is not consensus on every claim. Preserve conflicting requests. For a compound or repeated concern, verify each material clause has a concrete resolution criterion; pointing to a related theme is insufficient if it addresses a different mechanism. Short-horizon or static sensitivity evidence does not automatically resolve a longitudinal deployment concern.

Each theme's Markdown contains the analysis and concern-level resolution details. Keep detailed per-concern assessments in their existing analysis files, while making all material conclusions available through the theme content shown by the viewer. Cross-references may save space in a later response, but every reviewer still needs a direct answer and any indispensable evidence locally.

Maintain one continuously updated overview, not separate initial/subsequent reports. The viewer already labels it **Overview**; do not add another title inside its Markdown. Write for a researcher deciding where to start:

1. Begin with the manuscript path/version, overview update timestamp, and source review dates. Distinguish creation/modification dates from a capture or receipt date; never invent a missing date. State a material manuscript-version uncertainty briefly.
2. State the number of unique themes, reviewers, concerns, and tasks, with current task status counts. Compute these from the workspace rather than assuming previous counts still hold.
3. List all themes with links, unique reviewer counts/IDs, and related task links. Order by descending unique reviewer count, breaking ties by stable theme number. Apply this order to the theme data too; never renumber IDs to match a new order.
4. Give a short **Where to start** list of concrete actions and why they matter. Distinguish what the paper already establishes from what still needs verification or measurement. Link every substantive issue to its exact concern, theme, or task; do not leave unexplained topics such as “cold start” floating in the overview.
5. Show useful answers already available in the paper: the reviewer question, the existing answer with precise paper references, and the linked follow-up. Avoid vague labels such as “supported with boundaries”; say exactly what is established and what remains unknown.

Keep extraction procedures, input exclusions, validation details, agent coordination, and workflow explanations in provenance/audit files, not the overview. The overview is a navigation and decision aid, not a development log. Do not imply acceptance is assured. Verify that overview links actually open the intended concern, theme or task in the browser.

## Propose work and verify

Create tasks for concrete deliverables, linking all concerns they resolve. All newly generated tasks start `proposed`; only user agreement moves them to `pending`. Use high/medium/low priority and effort independently. Explain the priority in `note`, including dependencies or experiment lead time when relevant. Separate checking whether evidence already exists from committing to new experiments. Keep low-impact wording corrections below central validity/evidence issues.

Validate all files and links, unique IDs/numbers, annotation-to-concern correspondence, original checksums, exact text preservation, and empty drafts for an analysis-only run. Review coverage against the full initial reviews, including compound requests and repeated limitations. Check no theme claims more reviewers than its links support.

If independent reviewers are requested, ask for concrete omissions, mismatched evidence, and misprioritized work with source references; unsupported suggestions do not become tasks. Reconcile their findings and record the decisions. Open the resulting workspace through the UVX viewer, refresh the actual user-facing tab, and verify the displayed title, themes, annotations, and tasks before reporting completion.
