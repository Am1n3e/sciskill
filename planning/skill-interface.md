# SciSkill interface

[Planning index](index.md)

Status: intended behavior agreed; documented on local preview, agent implementation deferred.

## Entry point

Invoking /sciskill without an action lists available tasks as bullet points and asks “What would you like to do?” It does not begin execution until the user chooses.

## Initial task list

- Check references: audit bibliography metadata against scholarly sources.
- Plan a rebuttal: organize reviewer concerns into a response plan.

## Approved presentation tokens

- `/sciskill bib-lint paper.bib`
- `/sciskill plan-rebuttal reviews.md`

Homepage examples now use these action tokens with copy buttons. They describe the intended finished interface; implementation, routing, input validation, and detailed workflows are deferred. Keep readiness notes here, not as progress labels in the public-facing page. Bare `/sciskill` remains a help fallback and is not promoted as the main homepage example.

## Approved setup and page refinements

The intended interface includes `/sciskill init`: check required tools, install missing dependencies, and reuse existing installations. A compact copyable setup step follows the centered installation command and precedes the two action sections. Backend dependency handling remains to implement before publication.

Approved command presentation refinement: use `bib-lint` as the reference-checking action token. The established namespace remains `/sciskill`. Homepage presents invocation-only terminal panels, not synthetic results or logs. Underlying agent skill implementation remains deferred.

## Latest action layout and draft outputs

Applied three matching sequential action sections: 01 Initialize, 02 bib-lint, 03 Plan your rebuttal. Skills navigation now lands at Initialize (`#toolkit`). Removed compact init treatment. Action terminals have no AGENT header or copy control; the centered npx installer retains its copy icon. Each action shows its command and a short static representative response, not live execution.

Draft representative output text is provisional and must be replaced or validated against the implemented workflow before publication:

- Init: “Required tools are ready.”
- bib-lint: “Audit complete. Open the report to review findings and source evidence.”
- Rebuttal: “Response plan ready. Review concerns, supporting evidence, and proposed responses.”

The user will review/refine these samples later. No readiness badges or progress-tracker text are added to public UI. Backend remains deferred.
