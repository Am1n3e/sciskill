---
name: sciskill
description: Analyze scientific peer reviews against the submitted manuscript, annotate actionable passages, and produce linked themes and proposed rebuttal tasks for Rebuttal Desk. Use for Science Skills plan-rebuttal workflows.
---

# Science Skills

For `plan-rebuttal`, turn initial reviews and the manuscript into an evidence-grounded response plan. With no action, briefly describe this capability and ask for the reviews and manuscript. Do not advertise unimplemented actions.

Read [the analysis workflow](references/plan-rebuttal.md) and [the workspace contract](references/workspace.md) before running it. Use the existing Rebuttal Desk importer and validator; the tool runs with `uvx` and stores research data outside its package.

The manuscript, including its available appendix/supplement, is required. Identify the version used. In an initial-review run, use only the initial review entries: exclude author responses, later exchanges, decisions informed by them, and prior rebuttal analyses. If a captured initial entry was subsequently edited, record that uncertainty. Do not silently treat a revised manuscript as the submission.

Preserve original review headings and content; annotate their exact passages in `annotated_content`. Check the original checksum and exact preservation. Keep the reviewer's stated request distinct from your interpretation. Describe evidence that would resolve the issue, not a prediction of the reviewer's vote.

Produce annotations, linked analysis with precise manuscript references, cross-review themes, an overview, and proposed tasks in the current workspace format. Preserve existing human decisions and drafts on reruns. Do not generate response drafts, run experiments, modify the manuscript, or mark tasks accepted/done unless requested. Put any missing evidence or unresolved interpretation in the analysis.

Prioritize threats to validity, fairness, reproducibility, and the central claims. Effort is a separate scheduling dimension. Capture small actionable items without letting them displace material issues. Avoid copying every mention into another task; a shared task may answer several concerns, but each concern needs an explicit resolution criterion.

When independent review is requested, give reviewers the skill, allowed raw inputs, and generated artifacts. Have them separately audit coverage, evidence, and priorities. Reconcile findings against the sources, retain unresolved disagreements, and revise only where supported. The final check asks whether the plan answers each original concern, not merely whether its prose sounds convincing.
