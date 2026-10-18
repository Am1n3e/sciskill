# Rebuttal Desk workspace contract

Resolve the installed Rebuttal Desk package or the checked-out `tools/rebuttal-desk` directory. Local source invocation:

```sh
uvx --from /absolute/path/to/tools/rebuttal-desk rebuttal-desk import-openreview initial-reviews.html new-workspace
uvx --from /absolute/path/to/tools/rebuttal-desk rebuttal-desk validate new-workspace
uvx --from /absolute/path/to/tools/rebuttal-desk rebuttal-desk view new-workspace
```

Do not claim a published package/source exists without checking. A unique built wheel may be used with `--from` when previewing changed tool code.

The importer writes one YAML per initial review, with `sections` containing `heading`, immutable `content`, and `annotated_content`. It also stores source identity, timestamps, a checksum, and a conversation list. For an initial-only run that list is empty. Original headings/content remain byte-for-byte identical as strings. Use the package's checksum function; do not reset a checksum to conceal edits.

```yaml
heading: Questions
content: Please clarify how the gates are generated.
annotated_content: <science-skills-annotation id="a1-C1" type="clarification">Please clarify how the gates are generated.</science-skills-annotation>
```

Allowed tag attributes: `id`, `type`, optional `subtype`. Types: `clarification`, `change_request`. Subtypes for change requests: `manuscript_change`, `additional_experiments`. No nested/overlapping tags; all IDs must be globally unique and have matching manifest concerns. Original Markdown remains inside the wrappers.

The `workspace.yaml` shape is:

```yaml
version: 1
source: openreview
title: Paper title
presentation:
  character_limit: 10000 # use the confirmed venue limit, or null if unknown
reviews:
  - id: a1
    label: Reviewer a1
    document: reviews/source-id.yaml
    concerns:
      - id: a1-C1
        title: Gate construction
        related: [] # IDs of other concerns sharing this issue
        analysis: concerns/a1-C1/analysis.md
        response: concerns/a1-C1/response.md # empty for analysis-only runs
analysis:
  overview: analysis/overview.md
  themes:
    - id: gate-reliability
      number: 1 # stable positive integer, not an array position
      title: Gate reliability
      content: analysis/gate-reliability.md
      reviewers: [a1] # explicit; exactly the owners of linked annotations
      annotations: [a1-C1]
      tasks: [1]
tasks:
  - id: 1 # stable unique positive integer
    title: Document gate construction and check its evidence
    annotations: [a1-C1]
    status: proposed
    priority: high
    effort: medium
    note: Explain the concrete deliverable and why it matters.
    external_link: null
```

Statuses: `proposed`, `pending`, `in_progress`, `done`, `not_doing`. Theme task links use the same numeric IDs. Document paths are workspace-relative and cannot escape the workspace. The loader expects the analysis and response files to exist, even when a response is empty. It renders theme and overview Markdown, while concern panes link to themes.

Overview and theme Markdown can link directly to `#REVIEWER/CONCERN-ID`, `#theme-THEME-ID`, or `#task-NUMBER`; `#REVIEWER` opens the full review. Use the exact persisted IDs. The viewer opens the corresponding tab and expands a linked theme. Theme display order is descending unique reviewer count, then stable theme number.

Keep provenance and audit results in workspace-local YAML/Markdown. Detailed reasoning fits the existing Markdown content files; do not expand the UI schema merely to store prose. If a new attribute is necessary, document and validate its meaning without duplicating a derived count or a source field. Do not include personal review content in the distributable skill.
