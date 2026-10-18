# Homepage

[Planning index](index.md)

Status: discussion draft. Review the complete plan before applying website changes.

## Agreed direction

- Keep Astroship's free theme as the visual foundation.
- Remove the astronaut illustration.
- Give Science Skillset its own homepage structure and identity; do not reproduce the reference site's format.
- Give each tool its own section on the homepage.
- Discuss the homepage first, then individual tool and skill pages.
- Collect decisions here and apply them together after review to reduce churn.

## Purpose

Provide tools and skills that let researchers use AI agents to move faster through repetitive, detail-heavy research tasks. Bibliography auditing is a concrete example: checking a hundred citations requires many small comparisons that benefit from automation.

## Proposed homepage direction — not yet agreed

- Explain the practical benefit in plain language.
- Use bibliography auditing as a concrete example.
- Introduce available tools through the tasks they help researchers complete.
- Let the purpose emerge from concrete workflows rather than opening with a defense of AI in science.

## Additional suggestions — not yet agreed

- Give each tool section a consistent set of useful details: the task, required input, concrete output, availability, and a link to its own page.
- Explain how tools and agent skills work together, including whether each tool can be used directly.
- Provide a clear starting action for a new visitor.
- Link to evaluation and limitations without crowding the homepage.

## Open decisions

- Exact headline and introductory copy.
- Homepage section order and level of detail.
- What replaces the astronaut: no illustration, an output example, or another visual.
- How tools, agent skills, and their availability should be presented.
- Structure of individual tool and skill pages, to discuss after the homepage.

## Header — current discussion

- Agreed: use “Skills” rather than “Tools” as the navigation label.
- Proposed: “Science Skillset” on the left; “Skills”, “Getting started”, and “GitHub” on the right. Remaining header choices await confirmation.
- Continue reviewing the homepage from top to bottom, one item at a time, without sub-agents. Record decisions before implementation.

## Live editing approved

The user approved applying discussed items directly and refreshing the local preview, superseding the previous planning-only hold for those items. Header approved and applied: Science Skillset; Skills; Getting started; GitHub. GitHub currently links to the author profile because the collection repository has not been created.

Header refinement applied: Getting started, Skills, GitHub. Getting started and Skills navigate to homepage sections; homepage serves as the introduction and onboarding surface. Existing guide files retained pending later content review.

Applied: remove the hero eyebrow line “A toolkit for scientist-led work” and its green dot.

Applied approved hero headline: “Agent skills and tools for scientists.”

Applied approved hero description: “Keep your focus on the science. Let your agent handle the groundwork.”

Refined approved hero description: “Keep your focus on the science. Let your agent handle the grunt work.” Replaces “groundwork”.

Applied: remove the hero “Explore the toolkit” button and “You set the direction. You make the decisions.” note.

Applied first hero illustration draft for live review: scientist at an equation-filled chalkboard; small robot sweeps chalk dust. Replaces astronaut. User reviews illustrations in the webpage itself.

Applied illustration refinement: monochrome black ink on white, sparse hatching, no colored board or painted shading. Scientist and sweeping robot composition preserved. Generated with the built-in image tool.

Applied: whiteboard now shows Transformer attention, projections, multi-head attention and feed-forward equations, preserving the monochrome scientist and robot scene.

Approved naming update applied to page: Science Skills (formerly Science Skillset). Chosen agent command name: SciSkill, with /sciskill as the proposed lowercase invocation; routing and actions remain unimplemented. Existing URL unchanged during local design review.

Applied approved installation section: replaced “One entry point. Choose your task.” and the bare-command help menu with a centered, copyable `npx skills add Am1n3e/science-skills` command. Marked “Planned installation · not released yet” because the repository and skills are not published. The agent's help behavior remains an interface decision, not a homepage section. Both homepage copy buttons now work independently.

User correction applied: remove the installation readiness label from the page and use an icon-only copy button with an accessible label and clipboard feedback. The page is the intended finished public presentation; keep readiness status in these planning notes, not in product UI. This requirement applies to future work and handoffs. Repository and skill release remain pending outside the page.

## Approved action sections applied

After the centered installer, show two substantial sequential sections: “Check your references” and “Plan your rebuttal.” Each has a copyable action command, explanation, honestly labeled illustrative result, and detail-page link. The Skills anchor remains `#toolkit` at the first action. Removed generic examples introduction, tabs, principle strip, duplicate toolkit cards, readiness/catalog notices, and the generic approach section, including its leftover hero CTA. Retained the lower bib-lint setup section pending subsequent review. The preview depicts the intended finished product; underlying skill implementation remains deferred.

Applied icon cleanup: replaced the orange asterisk favicon with a plain monochrome S, removed hidden asterisk marks from header/footer and deleted the unused Mark component. Versioned the favicon URL to refresh browser caches. Other content unchanged.

## Approved setup and page refinements

The intended interface includes `/sciskill init`: check required tools, install missing dependencies, and reuse existing installations. A compact copyable setup step follows the centered installation command and precedes the two action sections. Backend dependency handling remains to implement before publication.

Applied header brand “Science Skills”; Home replaces Getting started and links to the homepage top. Removed the bottom bib-lint local setup section and unused setup constant. Footer now contains only About the author, linking to the existing author profile. Visible Astroship credit removed; LICENSE and THIRD_PARTY_NOTICES retained. Action sections remain unchanged. Readiness belongs in planning documents; publication follows implementation.

Applied terminal presentation refinement: reference section heading is “bib-lint” with `/sciskill bib-lint paper.bib`; rebuttal retains `/sciskill plan-rebuttal reviews.md`. Each section has one terminal-style invocation panel with accessible copy icon. Removed all mock comparison/reviewer results and their example/fictional labels, with no fabricated execution logs substituted. Hero, install, init, header, and footer preserved.

## Latest action layout and draft outputs

Applied three matching sequential action sections: 01 Initialize, 02 bib-lint, 03 Plan your rebuttal. Skills navigation now lands at Initialize (`#toolkit`). Removed compact init treatment. Action terminals have no AGENT header or copy control; the centered npx installer retains its copy icon. Each action shows its command and a short static representative response, not live execution.

Draft representative output text is provisional and must be replaced or validated against the implemented workflow before publication:

- Init: “Required tools are ready.”
- bib-lint: “Audit complete. Open the report to review findings and source evidence.”
- Rebuttal: “Response plan ready. Review concerns, supporting evidence, and proposed responses.”

The user will review/refine these samples later. No readiness badges or progress-tracker text are added to public UI. Backend remains deferred.

Applied naming cleanup across active source, configuration, README, package/lock, and notices: Science Skills, `/science-skills/`, and `#skills`. Detail-page return links and eyebrows now use skills terminology. The new preview URL is `http://127.0.0.1:4321/science-skills/`. Existing guide routes remain valid. Historical decisions above retain former names; this entry supersedes their current route/name references.
