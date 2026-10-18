# Cross-review analysis — discussion draft

## Agreed purpose

A paper-wide Analysis tab groups common themes across reviewers. Each theme has a title, analysis content, reviewer count, and links to relevant annotations and tasks. Count each reviewer once per theme.

## Proposed storage

Add `analysis.themes` to workspace.yaml. Each theme stores a stable unique ID, title, a path to a Markdown content file, reviewer IDs, annotation IDs, and task IDs. Reviewer IDs are explicit in `reviewers`; the displayed count is the number of unique IDs in that list. Tasks may be shared between themes; annotations may also belong to more than one theme.

```yaml
analysis:
  overview: analysis/overview.md
  themes:
    - id: theme-1
      number: 1
      title: Hardware compatibility
      content: analysis/hardware-compatibility.md
      reviewers: [GruC]
      annotations: [GruC-C3, GruC-C9]
      tasks: [1]
```

The example is illustrative: two annotations from GruC count as one reviewer. Task IDs must reference existing workspace tasks; annotation IDs must reference existing annotations. Source review text remains unchanged.

## Scope

Data proposal only. No viewer changes or automatic analysis implemented at this stage. Review the model before implementation. Do not add extra fields or features without discussion.

## Analysis content

Each theme links through `content` to a workspace-relative Markdown file containing the actual analysis. The YAML holds the theme metadata and links; the Markdown file holds the discussion of the relevant feedback and what needs addressing. This is a proposal, not generated analysis.

The title names the theme; all detail belongs in the linked Markdown file. There is no separate summary field. Researchers can open the Markdown in their own viewer.

Reviewer IDs are explicitly stored at the user’s request. Validate that they reference workspace reviewers and match the reviewers represented by the linked annotations; show the unique reviewer count from this list. Do not store a separate numeric count.

## Implemented presentation

Analysis is a top-level tab. Each theme displays its Markdown, explicit reviewer IDs and count, annotation links, and task links. Concern panes retain Response and link to their matching themes instead of a per-concern Analysis tab. The local example uses four themes based only on the currently annotated reviewer; no cross-review consensus is invented.

Theme title, reviewer count/IDs, annotations, and tasks remain visible. The Markdown analysis is expandable and initially collapsed to accommodate long content.

Use “Related reviews” as the theme UI label for annotation links; links still target the specific review concern.

Concern theme links appear as clickable “Theme: [title]” chips beside the classification chip, not in the Response tab strip.

Number themes in workspace order as Theme 1, Theme 2, etc.; show the same number in Analysis headings and concern theme chips. Stable underlying IDs remain unchanged.

Theme numbering is persisted in a required positive unique `number` field. UI headings and chips use this value, not array position, so reordering themes preserves their numbers.

Remove the sole remaining Response tab in concern panes; show the response box directly. Keep Refresh and the theme chips.

Move Refresh into the concern pane header beside Close; remove the empty tab strip and its extra divider.

Replace per-concern Refresh controls with a single app-header Reload button, since reload rereads the whole workspace.

Use one expandable theme header containing the number/title, reviewer count/IDs, Related reviews, and Related tasks. Clicking the header expands the analysis content; remove the separate Analysis expander.

Theme header uses two rows: number/title left and reviewer count/IDs right on row one; Related reviews and Related tasks on row two.

Analysis is the first tab and default view on opening the app, followed by Reviews and Tasks.

An optional workspace-relative Markdown `analysis.overview` file renders at the top of Analysis before the themes, connecting the overall findings.
