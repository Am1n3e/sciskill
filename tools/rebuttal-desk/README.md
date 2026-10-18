# Rebuttal Desk

A standalone, read-only local viewer for reviews, concern-level analysis, response drafts, related concerns, and an assembled response. It does not analyze reviews or generate responses. Edit the workspace files in your editor, then click Reload.

```sh
uvx sciskill rebuttal init ./my-rebuttal
uvx sciskill rebuttal validate ./my-rebuttal
uvx sciskill rebuttal view ./my-rebuttal
# automation / headless use:
uvx sciskill rebuttal view ./my-rebuttal --no-browser --port 8765
```

`init` creates a small, entirely synthetic template and refuses to overwrite an existing path. You can create multiple independent workspaces outside this repository. `view` binds only to 127.0.0.1, prints the URL, and opens your browser unless disabled. Stop with Ctrl-C. The default port is chosen automatically. No write endpoint exists.

## Import OpenReview

Capture the **rendered** OpenReview forum page after all reviews and replies load, then pass the saved HTML to the importer:

```sh
uvx sciskill rebuttal import-openreview ./openreview-discussion.html ./my-rebuttal
uvx sciskill rebuttal view ./my-rebuttal
```

The importer refuses to overwrite an existing directory. It writes `workspace.yaml` and one `reviews/<review-id>.yaml` per initial review or decision. Each review file contains its original sections and a `conversation` of `author_response` and `reviewer_comment` entries. Every entry preserves its ID, author, title, source type, timestamp, reply target, and ordered field headings with content converted to Markdown. Formula TeX is recovered from KaTeX annotations when available.

Conversations are sorted by creation time, with the ID breaking equal-time ties. The displayed timestamp and its original text are retained; captures without timezone information do not acquire an invented timezone. Reply targets are resolved from explicit “Replying to” headings when present, otherwise from HTML nesting. Ambiguous reply targets, missing timestamps, and threads that cannot be associated with a review cause an import error instead of silently losing content. Separate threads started by the same reviewer or editor are included in that review's conversation; their root has no reply target.

No concerns, analysis, or response drafts are inferred by import. Action editor labels use the role and exported ID without a personal name. The import is offline and does not execute scripts or fetch links from the HTML. An initial HTML shell without loaded comments is rejected; the importer cannot recover content missing from the capture.

## Workspace format

`workspace.yaml` is UTF-8 YAML:

```yaml
version: 1
title: My rebuttal
source: openreview
presentation:
  character_limit: 10000
reviews:
  - id: aB12
    label: Reviewer aB12
    document: reviews/review-id.yaml
    concerns: []
```

Each review file stores the original review and its conversation together. The importer also writes `content_checksum` (SHA-256) over all initial section headings and original content in order:

```yaml
id: review-id
reviewer_id: aB12
title: Original review title
author: Reviewer aB12
source_type: Review
created_at: '2025-01-01T10:00'
timestamp_text: '01 Jan 2025, 10:00'
content_checksum: sha256:c5f9af2a32dad4c80d16159cfba8206ca697c81036aa8e3a577442d669c5fc22
reply_to: null
sections:
  - heading: 'Claims And Evidence:'
    content: |
      Original review text.
    annotated_content: |
      Original review text.
conversation:
  - id: response-id
    type: author_response
    author: Authors
    title: Clarification
    source_type: Official Comment
    created_at: '2025-01-02T09:00'
    timestamp_text: '02 Jan 2025, 09:00'
    reply_to: review-id
    sections:
      - heading: 'Comment:'
        content: |
          Original author response.
```

Original `content` remains the source of truth. Each initial section has a separate `annotated_content` attribute, initially identical. The viewer renders validated annotation passages as colored underlined links: blue for clarification and purple for change request. Clicking a passage toggles its response pane; theme chips link to shared analysis. Turning Annotations off shows the original review. On every load, the original headings and content must match `content_checksum`, or loading fails. YAML formatting, annotations, and conversation entries are excluded from this checksum. This detects accidental source edits; it is not protection against someone rewriting both the source and checksum.

Concerns can later be added to a review with `id`, a concise `title`, the original `question`, `analysis` and `response` Markdown file paths, and `related` concern IDs. Original review content remains separate from those drafts. Existing JSON workspaces remain readable.

All document files must exist and use `.md`, `.txt`, `.html`, or structured `.yaml`. Paths are relative to the workspace and must resolve within it, including symlinks. IDs use letters, digits, hyphens, and underscores; concern IDs are globally unique. Related IDs must exist anywhere in the workspace. `presentation.character_limit` is a positive integer or null (no limit). The manifest and each file are limited to 2 MB. Review lists must be nonempty; a review can have no concerns.

Markdown supports headings, lists, fenced code and tables. HTML is sanitized using an allowlist; scripts, active attributes, remote images and styles are removed. Formula source remains readable text; this extraction deliberately has no math typesetting runtime. Browser assets are packaged locally; no CDN, network font, or browser dependency download is required. Python dependencies are resolved by uv on first installation; subsequent viewer use works offline with its environment already available.

Only explicit UI assets and validated, rendered workspace data are served. Raw workspace files, other repository paths, and directory listings are not exposed. There are no CORS permissions, and Host validation rejects rebinding-style hosts. The viewer is intended for trusted local use, not multiuser hosting or exposing via a tunnel. Other local processes can access a loopback server while it runs.

## Response semantics

Response panes show the draft directly, with links to related themes in Analysis. Related links select the corresponding reviewer and expand the concern. The assembled response concatenates nonempty response drafts in manifest order, separated by two newlines. Blank or `TBD` / `[TBD]` responses are excluded. “Drafted” records the presence of text, **not** whether a concern is resolved. Word counts split on whitespace; characters count Unicode code points including whitespace, not bytes or grapheme clusters. Limits apply separately to each review's assembled response. A limit indicator does not change files.

## Development

```sh
uv run --project tools/rebuttal-desk python -m unittest discover -s tools/rebuttal-desk/tests -v
uv build tools/rebuttal-desk
```

The stylesheet was extracted from the author's local Rebuttal Review Desk. The general workspace JavaScript and Python CLI replace its paper-specific review constants, HTML workbench assumptions and validation script. No original reviews, manuscript identifiers, private analysis or response content are included. The generated template is authored from scratch. Distributed under MIT; browser dependency vendoring is unnecessary because rendering happens in Python.

## Presentation and comments

The viewer always uses its OpenReview-style review cards and threaded comment grouping. There is no alternate viewer or selectable profile. Review/comment/concern/analysis/response data remains independent of presentation. `presentation` accepts only `character_limit`: a positive integer, or null to disable the limit. If omitted, the limit is 10,000 characters per assembled response.

Rendering currently uses sanitized Markdown/HTML; OpenReview-style layout does **not** imply exact OpenReview Markdown/math renderer parity. Exact parity requires further work and fixtures. No external parser is loaded in the browser.

Reviews optionally include `comments`: a list of `{ "id": "comment-1", "label": "Author clarification", "document": "comments/clarification.md" }`. Comments use the same file containment and rendering rules as reviews. Drafts are edited in workspace files; the agent analysis workflow is documented in `skills/sciskill` at the repository root.

## Annotations

Annotation rendering is part of the packaged viewer. Use `rebuttal-desk init` to create a runnable synthetic workspace; review the analysis skill under `skills/sciskill` in the collection repository for the annotation workflow.

Annotations use `<science-skills-annotation id="..." type="clarification|change_request">...</science-skills-annotation>` within `annotated_content`. They may include an optional nonempty `subtype` attribute for a finer work category; supported values are `manuscript_change` and `additional_experiments`.

## Reviews and Tasks views

The title sits above Analysis, Reviews, and Tasks tabs. Analysis opens by default and renders a Markdown overview followed by numbered themes with related reviews and tasks. Reviews keeps its reviewer picker inside the view. Tasks has an independent reviewer filter that defaults to All reviewers; switching views preserves each selection without carrying it into the other view. Tasks linked to multiple reviewers appear once and match any associated reviewer.

The manifest may contain a `tasks` list using the agreed fields (`id`, `title`, `annotations`, `status`, `priority`, `effort`, `note`, `external_link`). Task IDs are unique; annotation references must exist. Status is proposed, pending, in_progress, done, or not_doing. Priority and effort are low, medium, or high. External links are optional HTTP(S) URLs. The task view sorts high priority first and preserves file order for ties. Task data is read-only; edit YAML externally. No agent-generated tasks are created automatically.
