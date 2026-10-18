# bib-lint UI and skill review

Reviewed 18 October 2026. The findings below describe the original Streamlit interface. The subsequent UI port was approved and implemented; see the implementation record at the end. The skill workflow remains to implement.

## What was inspected

- Current bib-lint source, CLI, workflow controls, report/evidence readers, and agent-evidence contract.
- Live overview and reference detail at `http://127.0.0.1:8501/`, using an existing saved local audit. No new scholarly lookups were run.
- The Science Skills entry point and existing first-use/distribution plans.
- Rebuttal Desk's outer interface as the visual comparison.
- Relevant [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).

Validation: 25 tests pass across `test_ui.py`, `test_viewer.py`, and `test_agent_review.py`. Browser inspection identified layout issues that those functional tests do not check. The saved audit predates the current report schema; its outcomes are historical evidence, not a new evaluation of today's providers.

## Findings, ordered for discussion

1. **The bib-lint skill action is missing.** `skills/sciskill/SKILL.md:8` implements only `plan-rebuttal`; there is no bibliography-audit workflow reference or action. Existing planning describes the intended behavior, but the installed entry point cannot yet perform the advertised `/sciskill bib-lint` workflow. `init` is also an existing, unimplemented collection-level requirement.
2. **Summary values are clipped.** `../bib-lint/src/bib_lint/viewer/app.py:114` places nine counters in one row. At the current browser width, labels and values truncate. Use a compact responsive summary; preserve access to the complete status breakdown.
3. **There is no direct queue for all references needing attention.** `../bib-lint/src/bib_lint/viewer/app.py:122` intentionally filters Invalid/Unresolved and request failures. It excludes Needs review and Partial match when there is no failed source request. In the inspected saved audit, six such entries disappear. Add or replace this with a clearly named Needs attention filter; keep request failures distinguishable from confirmed metadata discrepancies.
4. **The result lacks a clear audit identity at the top.** `../bib-lint/src/bib_lint/viewer/app.py:54` starts with the tool title and counters. Report/cache paths live in the sidebar at line 267; source scope and audit time are not presented as a readable summary. Show the bibliography/workspace, audit timestamp when recorded, and whether checks cover all entries or AUX-selected citations. Unknown or missing historical metadata must stay unknown.
5. **Reference details lead with raw data.** `../bib-lint/src/bib_lint/viewer/app.py:334` displays expanded entry JSON before corrections and differences. The citation key, full author list, and source count also precede the actual finding. Put the issue, evidence, and proposed correction first; retain exact raw data in the existing technical views. Keep the shared app header and tool identity visible in detail views.
6. **Reload and rechecking are easy to confuse.** `../bib-lint/src/bib_lint/viewer/controls.py:114` uses Refresh for a new verification that fetches sources, while `../bib-lint/src/bib_lint/viewer/app.py:282` uses Reload to reread saved results. Make those effects explicit and use one consistent top-level Reload control for disk changes.
7. **First-use documentation is incomplete.** `../bib-lint/README.md:1` contains only a brief description. It does not show the UVX launch/verify/view journey, the audit folder, AUX scope, interrupted runs, or how agent evidence reaches the viewer. The skill and documentation should share a tested execution contract.

## Skill workflow to define

Use the existing `/sciskill` entry point with a `bib-lint` action, preserving the approved single-command namespace.

1. Resolve the `.bib` input and optional compiled `.aux`; explain all-entry versus cited-only scope. Choose an audit directory without changing the input files.
2. Resolve the approved tool distribution/version and run it through UVX. Parse the CLI's structured final result and handle interrupted/partial runs; do not treat process exit zero alone as complete verification.
3. Summarize confirmed discrepancies separately from ambiguous matches, unsupported fields, missing records, and source failures. A failed lookup does not prove a reference is invalid.
4. Use primary-source evidence to investigate unresolved or conflicting items. Preserve publication-version distinctions and abbreviated author-list semantics; avoid treating normalized typography alone as a factual correction.
5. Write agent findings using the existing entry-bound evidence contract: `citation_key`, `entry_sha256`, status, timestamp, checked fields, summary, evidence URLs/support, comparisons, and limitations. Preserve automated consensus separately. The tool already supports this overlay and rejects stale evidence; the missing piece is a reusable agent workflow to produce it.
6. Return a useful action summary and open the correct audit in the browser. Verify the displayed results and links. Corrections remain proposals unless the user explicitly asks to edit the bibliography.

The exact command source/version and agent-evidence writing/validation method must be settled and exercised on a local example. No additional providers or bibliography rewriting are proposed as part of this review.

## Proposed common UI baseline

Use the Rebuttal Desk outer interface as the baseline for Science Skills tools:

| Element | Common behavior |
| --- | --- |
| Header | Science Skills brand, tool title, current input/workspace, Reload at the top right |
| Typography and spacing | Same title/body hierarchy, readable line lengths, margins, and control sizes |
| Surfaces | Light neutral outer page, quiet borders, consistent panel and table styles |
| Navigation | Same tab treatment and focus states; tool-specific labels that describe the content |
| Status | Consistent chips with text; verified metadata, uncertainty, and request failure remain distinguishable |
| Long content | Wrapping or deliberate scrolling; readable totals without clipping |
| Evidence | Human-readable finding first; exact source data remains accessible |
| App controls | Tool actions take precedence over framework chrome; no Deploy control in the researcher workflow |

For bib-lint, a candidate structure is **Overview** and **References**, with input/setup controls grouped separately. This is a proposal, not an approved addition. Rebuttal Desk's OpenReview content styling remains specific to that content; the common baseline concerns the app around it.

Choose the smallest implementation that can deliver this baseline. Streamlit and Rebuttal Desk currently use different UI implementations; the user subsequently approved porting bib-lint to the same Python server and bundled browser approach as Rebuttal Desk. That approval supersedes the earlier styling-only proposal.

## Suggested implementation sequence

1. Agree the shared header, summary, navigation, and reference-detail reading order.
2. Apply the agreed UI to bib-lint and verify the overview, detail, empty, loading, and error states at the current browser width and a narrow width. Keep existing verification behavior and evidence integrity checks.
3. Implement the bib-lint action and its output contract, then exercise it end to end on a local example.
4. Keep the UI and skill work in separate commits, with browser verification before calling UI work done.


## Approved UI port and verification — 18 October 2026

The user requested replacing Streamlit with the same backend approach as Rebuttal Desk. Implemented in the bib-lint repository:

- Standard-library loopback HTTP server with bundled HTML, CSS and JavaScript; no frontend installation. The console command remains `bib-lint view`, with optional `--no-browser` for parity with the Rebuttal Desk launcher.
- Science Skills header, tool title, neutral light surfaces, consistent tabs and Reload placement. Overview uses responsive counters, input/report identity, saved-report modification time, scope and a full status breakdown. References supports search, unused/attention filters, direct links and evidence-focused details.
- Existing verification and job code retained. Browser actions support parse-only, verify, recheck, selected-key operations, open, stop and resume. Reload only rereads saved results. Session selections remain independent; running jobs can be reattached by opening their workspace.
- Existing reports, source bibliographies, automated/agent evidence separation and cache checksums retained. Raw responses and entry data display as text. Cached HTML is never executed. Source/provider behavior is unchanged.
- Streamlit-specific controls and tests replaced; the dependency and its unused transitive dependencies removed from the lockfile. Runtime browser assets are included in installed wheels and source distributions.

Verification: 398 offline tests and the isolated-install test pass. The installed test checks static assets and starts a zero-reference audit through the local API. Python lint, formatting, complexity and JavaScript syntax checks pass. Browser checks cover attention filtering, search, reference links, cached-response integrity, parse-only and actual zero-reference verification, followed by restoring the original saved audit. The visible preview runs from the built wheel through UVX on port 8501.

The bib-lint agent skill remains a separate work item. No source-provider changes, bibliography rewriting or publication are part of this port.
