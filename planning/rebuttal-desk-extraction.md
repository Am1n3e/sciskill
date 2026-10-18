# Rebuttal Desk phased extraction

## Phase 1 — packaging and launch checkpoint

Standalone Python package, rebuttal-desk console command with help/version and view, packaged placeholder HTML/CSS, loopback-only server, no workspace/data routes. Validate wheel assets and uvx launch from an unrelated directory before review. No source viewer/private data is included in this checkpoint.

## Phase 2 — viewer and workspace contract

Preserve the existing Rebuttal Desk layout and workflow. Review input manifest/loading boundary and OpenReview rendering parity before applying the extraction. Preserve original review, concern analysis/response, related links, Refresh, assembly, and truthful drafted counts. A nonempty response does not prove resolution. All input remains local and private; publish only reusable code and synthetic fixtures. Full provisional extraction is preserved outside the repository, not committed in phase 1.

## Phase 3 — minor editing

Discuss limited Markdown editing/save after viewer review. Do not implement editor or CodeMirror now.

Stop after each phase for user review. Underlying implementation precedes site publication. Readiness notes remain in planning, not the public landing page.

## Phase 2 implemented

Restored generalized read-only viewer with a versioned local manifest, explicit document paths, reviewer navigation, response-first drawers/analysis toggle, related concern links, Refresh, aggregate drafts and length counts. Added optional review comments and a separate `presentation` object. Profiles `generic` and `openreview` configure grouping/layout and default limits while loaded review data stays identical. Both currently use sanitized Markdown/HTML rendering; OpenReview exact Markdown/math parity remains unimplemented, with formula source displayed as text. No editor or save endpoint.

Validated profile data invariance/defaults/override/unknown rejection, comment path containment, manifest/files, sanitization, restricted server and independent workspaces. Synthetic fixture only; no private input data. Parent should visually review demo after package launch. Phase 3 remains deferred.

## User correction — one viewer

Removed the generic viewer/profile alternative and branching. OpenReview-style cards/threaded comments are always used. Presentation configuration now accepts only character_limit (default 10,000, null disables). Underlying review data remains independent of display. Earlier profile planning is superseded. Exact renderer/math parity and editing remain deferred.

## Corrected viewer acceptance target

Use synthetic input data to populate the original Rebuttal Desk visual layout, launched by the new uvx package. Do not substitute a simplified synthetic interface or show private reviews for acceptance. Current demo has two reviewers and a meta-review, five concerns, analysis and response files, related concerns, response-first drawers and assembled rendered responses. Uses original CSS and corresponding DOM classes. Exact OpenReview math/Markdown parity remains a later phase.
