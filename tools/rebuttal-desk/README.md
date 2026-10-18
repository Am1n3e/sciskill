# Rebuttal Desk

A standalone, read-only local viewer for reviews, concern-level analysis, response drafts, related concerns, and an assembled response. It does not analyze reviews or generate responses. Edit the workspace files in your editor, then click Refresh.

```sh
uvx --from ./tools/rebuttal-desk rebuttal-desk init ./my-rebuttal
uvx --from ./tools/rebuttal-desk rebuttal-desk validate ./my-rebuttal
uvx --from ./tools/rebuttal-desk rebuttal-desk view ./my-rebuttal
# automation / headless use:
uvx --from ./tools/rebuttal-desk rebuttal-desk view ./my-rebuttal --no-browser --port 8765
```

`init` creates a small, entirely synthetic template and refuses to overwrite an existing path. You can create multiple independent workspaces outside this repository. `view` binds only to 127.0.0.1, prints the URL, and opens your browser unless disabled. Stop with Ctrl-C. The default port is chosen automatically. No write endpoint exists.

## Workspace format

`workspace.json` is UTF-8 JSON:

```json
{
  "version": 1,
  "title": "My rebuttal",
  "presentation": {"profile": "openreview", "character_limit": 10000},
  "reviews": [
    {
      "id": "reviewer-1",
      "label": "Reviewer 1",
      "document": "reviews/reviewer-1.md",
      "concerns": [
        {
          "id": "concern-1",
          "title": "Clarify the comparison",
          "analysis": "concerns/concern-1-analysis.md",
          "response": "concerns/concern-1-response.md",
          "related": []
        }
      ]
    }
  ]
}
```

All document files must exist and use `.md`, `.txt`, or `.html`. Paths are relative to the workspace and must resolve within it, including symlinks. IDs use letters, digits, hyphens, and underscores; concern IDs are globally unique. Related IDs must exist anywhere in the workspace. `presentation.character_limit` is a positive integer or null (no limit). The manifest and each file are limited to 2 MB. Review lists must be nonempty; a review can have no concerns.

Markdown supports headings, lists, fenced code and tables. HTML is sanitized using an allowlist; scripts, active attributes, remote images and styles are removed. Formula source remains readable text; this extraction deliberately has no math typesetting runtime. Browser assets are packaged locally; no CDN, network font, or browser dependency download is required. Python dependencies are resolved by uv on first installation; subsequent viewer use works offline with its environment already available.

Only explicit UI assets and validated, rendered workspace data are served. Raw workspace files, other repository paths, and directory listings are not exposed. There are no CORS permissions, and Host validation rejects rebinding-style hosts. The viewer is intended for trusted local use, not multiuser hosting or exposing via a tunnel. Other local processes can access a loopback server while it runs.

## Response semantics

Response drawers open on the Response view, with an Analysis toggle. Related links select the corresponding reviewer and expand the concern. The assembled response concatenates nonempty response drafts in manifest order, separated by two newlines. Blank or `TBD` / `[TBD]` responses are excluded. “Drafted” records the presence of text, **not** whether a concern is resolved. Word counts split on whitespace; characters count Unicode code points including whitespace, not bytes or grapheme clusters. Limits apply separately to each review's assembled response. A limit indicator does not change files.

## Development

```sh
uv run --project tools/rebuttal-desk python -m unittest discover -s tools/rebuttal-desk/tests -v
uv build tools/rebuttal-desk
```

The stylesheet was extracted from the author's local Rebuttal Review Desk. The general workspace JavaScript and Python CLI replace its paper-specific review constants, HTML workbench assumptions and validation script. No original reviews, manuscript identifiers, private analysis or response content are included. The generated template is authored from scratch. Distributed under GPL-3.0-only, consistent with this repository; browser dependency vendoring is unnecessary because rendering happens in Python.

## Presentation profiles

The review/comment/concern/analysis/response data is venue-neutral. Change only `presentation` to switch display without rewriting documents. `profile` accepts `generic` (default, simple sections, no default length limit) or `openreview` (review card and threaded comment grouping, default 10,000-character limit). An explicit `character_limit`, including null, overrides the profile default. Rendering remains sanitized Markdown/HTML for both; OpenReview is a layout approximation, **not exact OpenReview Markdown/math renderer parity**. Exact parity requires further work and fixtures before claiming it. No external parser is loaded in the browser.

Reviews optionally include `comments`: a list of `{ "id": "comment-1", "label": "Author clarification", "document": "comments/clarification.md" }`. Comments use the same file containment and rendering rules as reviews. Profiles group comments differently; source data stays unchanged. Profiles do not select data adapters or execute code. Editor/save support and agent skills remain later work.
