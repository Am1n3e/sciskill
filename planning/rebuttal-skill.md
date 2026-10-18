# Rebuttal analysis skill

## Approved scope (18 October 2026)

Create the Science Skills rebuttal-analysis skill, exercise it on the SKILL.nb manuscript and initial reviewer entries, and have independent reviewers audit the analysis. Exclude prior author responses, later exchanges and existing rebuttal analyses. Use the existing viewer workspace format; extend it only when needed.

## Implementation

The public skill is `skills/sciskill/SKILL.md`, with workflow and workspace-contract references. Its current implemented action is `plan-rebuttal`. No-action invocation describes that capability and asks for the inputs. The remaining previously discussed actions are not claimed as implemented.

The process records input provenance, reads the manuscript and initial reviews, annotates exact actionable spans, evaluates each concern against precise paper evidence, groups shared issues into themes, and proposes prioritized work. Each assessment separates the explicit ask, underlying issue, evidence, remaining gap and sufficient resolution. Annotated source text remains unchanged after wrappers are removed, and original checksums remain valid.

The local run is stored under `.local/workspaces/skill-nb-analysis/`, outside tracked source. It contains original review YAML, annotated content, empty response drafts, per-concern assessments, theme Markdown, overview, proposed tasks, provenance and audit records. This uses existing content links rather than adding duplicate prose attributes to the UI schema.

## Verification and independent review

- Skill frontmatter and references validated using skill-creator's validator.
- Workspace checked with Rebuttal Desk and additional exact-span/ID/link/empty-draft checks.
- Independent passes cover blind initial analysis, source-evidence accuracy, and materiality/prioritization. Reports and reconciliation stay with the local research data.
- The actual UVX-served viewer is refreshed and checked using the generated workspace.

## Boundaries

The run does not generate final author responses, perform experiments, alter the manuscript, or mark proposed tasks accepted. Manuscript submission-version equivalence must be confirmed before interpreting evidence as information the reviewers had originally received. Initial review entries may have been edited after their creation date; this is recorded rather than inferred away.

No source data or analysis is included in the public skill, and nothing is published by this work.
