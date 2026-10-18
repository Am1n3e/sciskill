# Rebuttal annotation working log

## Working method

Develop the process interactively on the current example review. Annotate passages as they are discussed, and record the action, reasoning, corrections, and approval here after each step. Do not annotate the remaining reviews in bulk or create the reusable agent skill yet. Once the user approves the final example and process, turn the agreed workflow into an agent skill.

Use the fresh local OpenReview workspace (`.local/workspaces/openreview-fresh`), which contains only initial reviewer and action-editor reviews. Local review data stays ignored by Git; this log records the process rather than copying entire reviews.

## Agreed decisions

1. Preserve every original section heading and `content` unchanged.
2. Work in the separate `annotated_content` attribute in the same review file.
3. Verify `content_checksum` against all initial headings and content in order on every load. An original-content mismatch fails validation.
4. Identify passages that need to be addressed, including statements that are not phrased as questions.
5. Use exactly one of two action categories per annotation:
   - **Response:** the passage calls for an answer, explanation, or clarification.
   - **Change request:** the passage asks for a modification to the paper, experiments, analysis, or supporting material. Reporting that modification later does not add a second response category.
6. The category records what the reviewer asks for, not a commitment to fulfill it.
7. Start with these two categories; add categories only after discussing a concrete need.
8. Annotation IDs connect marked passages to later analysis and drafts.
9. The original content is the source of truth. Removing annotation markup from the annotated version must recover it exactly.

## Agreed annotation format

Use the project-specific `<science-skills-annotation>` wrapper inside `annotated_content`, with `id` and `type` attributes, plus an optional `subtype`. Each annotation has one type: `response` or `change_request`. Start with these minimal attributes; do not add more fields without discussion.

```html
<science-skills-annotation id="GruC-C1" type="change_request">Exact original passage.</science-skills-annotation>
```

## Proposals still to settle on the example
- ID naming and the concise topic label.
- Passage boundaries, including how to handle multiple issues in a paragraph.

## Iteration log

### Step 0 — Establish the working example and rules

- Created a separate fresh workspace retaining the initial three reviewer reviews and the action-editor review, with no conversations or drafts.
- Added separate annotation attributes and checksum verification; no passages have been annotated yet.
- Agreed to develop and record the workflow through the example before writing a skill.
- Next: select the first passage, agree its boundary and category, then apply the annotation and record the outcome here.

### Step 1 — Agree the annotation wrapper

- Reviewed the separate original/annotated content storage shape.
- User approved the shape and chose `science-skills-annotation` as the unique wrapper name.
- No review passages have been annotated yet.

### Step 2 — First annotation: explicit implementation request

- Example: Reviewer GruC, Requested Changes, the implementation-availability request.
- Applied ID `GruC-C1`, type `change_request`, in `annotated_content` only.
- Boundary: wrapped the complete sentence, leaving the Markdown list marker outside the tag.
- Reason: the reviewer explicitly asks for an artifact to be supplied, rather than only an explanation.
- Verified that removing the wrapper recovers the original section exactly. Original content and checksum remain unchanged; the workspace validates.
- This is the first annotated example for user review, not approval to annotate the rest or create a skill.

### Step 3 — Visual annotation preview for discussion

- Created an ignored, separate browser mockup using the selected review's existing layout; production annotation rendering is unchanged.
- Proposal: highlight the exact marked passage softly, show its action category alongside it, and open a flat Response/Analysis panel directly below when expanded.
- Preview includes the existing per-draft/overall counts and Hide drafts behavior. No analysis or response text was invented.
- Await user feedback on this visual before applying it to the actual viewer.

### Step 4 — Simplify the annotation presentation

- User rejected the expanded-panel mockup.
- Requested only a highlighted passage acting as a link.
- Removed the visible action-type label, chevron, and draft panel from the preview.
- Link destination/behavior beyond the passage anchor remains to discuss; no draft-opening behavior is implied.

### Step 5 — Link opens the response pane

- Clarification: removing the visible label and chevron does not remove the response pane behavior.
- The highlighted passage is the only trigger. Clicking it expands/collapses its Response/Analysis pane below.
- Updated the isolated preview accordingly; no extra type label or chevron is shown.

### Step 6 — Distinguish the expanded pane

- User requested a different background for the expanded response pane.
- Applied the existing editor palette's pale blue (`#f4f8fd`) with modest padding in the preview, keeping the highlighted-link trigger unchanged.

### Step 7 — Match OpenReview's editable-field background

- Verified OpenReview's `.form-control` background in its official source: `#fffaf4`. Its preview uses a distinct `#fffdfa`.
- User chose the editable-field background for the expanded annotation pane, superseding the pale blue mockup.

### Step 8 — Reduce the pink tint

- User found the exact OpenReview editor color too pink and requested less pink.
- Changed the preview pane to a near-neutral off-white (`#fafaf8`), superseding the exact editor color.

### Step 9 — Add a slight pink tint

- User requested slightly more pink than the neutral off-white.
- Adjusted the preview pane to `#fcf8f6`.

### Step 10 — Counts at the pane's top right

- User approved the slightly pink background.
- Moved per-draft word/character counts and overall character usage to the right of the reviewer/concern heading, on the same top row.
- Removed the separate counts row beneath the tabs in the preview.

## Saved visual example

The reviewed link/pane interaction is retained in `tools/rebuttal-desk/examples/annotation-preview.html`, using a minimal synthetic passage and the package stylesheet. It includes the agreed highlight, link-controlled expansion, Response/Analysis tabs, slightly pink background, counts at the top right, and Hide drafts behavior. It is a standalone visual example, not the production annotation renderer or the completed agent skill. Captured review content remains in ignored local files.

### Step 11 — Annotate the selected review completely

- Annotated Reviewer GruC only; the other reviewer files remain unchanged.
- Retained `GruC-C1` for the already reviewed code request.
- Added four `response` passages: numerical discrepancies (`C2`), hardware compatibility conclusion (`C3`), novelty/significance (`C4`), and the related-work comparison (`C7`).
- Added four more `change_request` passages: alternative pruning criteria (`C5`), attention-block extension (`C6`), reconciling reported numbers (`C8`), and hardware-usable sparsity (`C9`). There are nine annotations total: four response and five change request.
- Kept the mixed “fix or explain” directive as a change request because it explicitly requests correction; classification does not commit the authors to a particular resolution.
- Left the contribution summary, strength, quoted method excerpt, and categorical “No”/“None” fields unannotated. These provide context or verdicts rather than additional independent requests.
- Original text and checksum remain unchanged. Removing all wrappers exactly recovers every original section.
- Linked the annotation IDs to empty analysis/response files and concise topics for inspection; no substantive analyses or replies were generated.

### Step 12 — Distinct action colors, then underlines

- User requested separate colors for questions/explanations (`response`) and change requests.
- Response passages use blue and change requests use yellow/gold.
- User then requested colored underlines instead of filled highlights. The underlined passage remains the pane trigger; no visible type label or chevron.

## Browser definition of done

For every visual change, open the latest version in the user's browser, verify that the intended change is present, and only then report completion. A source edit, screenshot alone, or background build does not meet this requirement. Do not announce a browser refresh before it has actually happened.

### Step 13 — Connect the real viewer

- The UVX viewer now reads the actual annotated YAML, validates that removing wrappers exactly recovers source content, and renders nine linked passages for GruC.
- Verified in a newly opened visible browser tab that response underlines are blue, change-request underlines are gold, all backgrounds are transparent, and clicking a passage expands its linked pane.
- The pane uses the agreed pink-tinted background and counts at top right; analysis/response files remain empty.
- Closed the obsolete full-review static preview tab after opening the real viewer, avoiding confusion between versions.

### Step 14 — Show annotation boundaries

- User found adjacent same-type underlines visually ambiguous (especially concerns 5 and 6).
- Requested visible start/end brackets with an ID.
- Added UI-only opening markers such as `[C5` and a closing `]`, retaining type colors and the existing click target. These markers do not change original or annotated source text.

### Step 15 — Remove blue tab-strip background

- User approved the start/end bracket presentation.
- Removed the light blue background behind Response/Analysis tabs within annotation panes. The strip now inherits the pane's agreed background.

### Step 16 — Cream-white pane

- User requested replacing the pink pane with cream-white.
- Chose `#fffdf5`, a near-white with a subtle yellow tint rather than pink. Tab-strip background remains transparent.

### Step 17 — Always show the response box

- User requested a visible response text box even when a draft is empty.
- Response tabs now display the Markdown source in a text box with a minimum visible height; blank drafts show a blank box.
- The tool remains read-only at this stage; saving/editor controls are not introduced by this display change.

### Step 18 — Optional subtype on the annotation tag

- User chose to keep change-request subcategory information in the same HTML-style annotation tag, using an optional `subtype` attribute.
- Added parser support for a nonempty subtype when supplied, without changing the two main types.
- Subcategory vocabulary and assignments remain under discussion. No existing annotation has been assigned a subtype.

### Step 19 — Keep change-request subcategories minimal

- User narrowed the vocabulary to two work categories:
  - **Manuscript change:** add details, clarify text, revise claims, discuss limitations, or otherwise update the manuscript.
  - **Additional experiments:** run an additional experiment or set of experiments.
- Purpose: communicate the scale/type of work, particularly distinguishing new experimental work from manuscript revisions.
- Do not introduce analysis, artifacts, related work, or method as separate subcategories at this stage.
- Existing annotations have not yet been assigned these subtypes. Exact serialized values and how to handle mixed requests can be settled on the example.

### Step 20 — One combined label inside the expanded pane

- User requested the main type and subtype as one label in the expanded pane near its reviewer/concern heading.
- Display format: `Change request: Manuscript change` or `Change request: Additional experiments`; without an assigned subtype, show `Change request`. Response passages show `Response`.
- Chose serialized values `manuscript_change` and `additional_experiments` for the two agreed subcategories.
- The passage itself retains only the bracket markers and colored underline. Existing annotations remain without subtypes until the assignments are discussed.

### Step 21 — Rename Response and use one classification chip

- User found the main type “Response” ambiguous because all items eventually receive a response. Renamed it `clarification` (UI: Clarification); `change_request` remains the other main type. Response drafts/tabs and author responses retain their existing names.
- One chip appears below the reviewer/concern heading inside the expanded pane. Clarification is blue; change request is purple.
- Combined subtype wording uses a slash: `Change request / Manuscript change` or `Change request / Additional experiments`. Without a subtype, the single chip says `Change request`.
- Matched change-request underlines and boundaries to purple as well, removing gold from the current annotation presentation.
- Migrated the four clarification annotations in the local selected review; no original content or checksum changed. Subtype assignments are still pending.

### Step 22 — Apply subtypes to the selected example

- User requested applying the labels/subtypes and showing the annotated example in the browser.
- Assigned `additional_experiments` to alternative pruning criteria (`C5`), extending to attention blocks (`C6`), and demonstrating hardware-usable sparsity (`C9`). These imply developing/testing additional experimental variants.
- Assigned `manuscript_change` to reconciling reported numbers or explaining differences (`C8`); this marks the requested paper correction/clarification, without claiming experiments can never be necessary.
- Left code availability (`C1`) without a subtype: publishing code is not accurately represented by either of the two agreed work categories.
- The four clarification passages remain `clarification`. All original content and checksums still validate.

### Step 23 — Close control inside the pane

- Added an icon-only close button at the expanded pane's top right, as requested.
- Closing hides the pane, synchronizes the passage's expanded state, and returns keyboard focus to that passage. Clicking the passage still toggles it.
