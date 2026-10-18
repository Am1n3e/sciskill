# Science Skills planning index

Status: discussion and planning only. Implementation is on hold until the relevant plan is reviewed and approved.

## Work groups

| Plan | Scope | Status |
| --- | --- | --- |
| [Homepage](homepage.md) | Purpose, content, per-tool sections, visual direction | Discussing |
| [Tool and skill pages](tool-pages.md) | Individual pages and their shared structure | To discuss |
| [Repository and distribution](repository.md) | Repository organization, tool and skill packaging, installation | To discuss |
| [SciSkill interface](skill-interface.md) | Entry-point menu and action list | Intended behavior agreed |
| [First-use workflow](first-use.md) | From installing a skill to inspecting a result, starting with bib-lint | To review |
| [Skill installation](skill-installation.md) | skills.sh compatibility and installation instructions | Discussing |
| [Evaluation and evidence](evaluation.md) | Evaluation reporting, limitations, availability claims | To discuss |
| [Publishing](publishing.md) | GitHub Pages, deployment, release readiness | To discuss |
| [Rebuttal annotation working log](rebuttal-annotation-workflow.md) | Develop annotations on an example, record decisions, then write the skill after approval | Iterating with user |
| [Cross-review analysis](rebuttal-analysis.md) | Themes across reviewers, linked annotations and tasks | Discussing data |
| [Rebuttal task list](rebuttal-task-list.md) | Define paper-wide researcher-maintained tasks, then presentation | Discussing data |

## How we work

- Record each topic in its corresponding file; add a new file for a distinct work group when needed.
- Separate agreed decisions, proposals, and open questions.
- Do not treat a recorded proposal as approval to implement.
- Review the relevant plans together before implementation and identify dependencies.
- When approved, implement in coherent groups and record validation and completion in the corresponding plan.
- Keep the existing website and tool repositories unchanged during discussion; planning documents may be updated.

## Standing presentation requirement

The local website represents the intended finished public-facing page, not a progress tracker. The user will publish GitHub Pages after underlying implementation is complete. Do not add planned/not-yet-released notices to product UI during future work or handoffs. Track implementation readiness and publication dependencies in planning documents instead.

## Current names and routes

Public name: Science Skills. Source repository target and package: `science-skills`. Base path: `/science-skills/`; Skills fragment: `#skills`. Namespace: `/sciskill`, actions `init`, `bib-lint`, and `plan-rebuttal`. Earlier planning entries retain historical names as decision history; these current names supersede them. The physical local project folder remains `science-skillset`.

## Delegation scope rule

Every task handoff must explicitly state: implement only what the user has discussed and approved. No optional features, speculative extensibility, extra modes, or additional functionality. If a material scope decision is missing, bring it back for discussion rather than inventing a feature. OpenReview is the only current viewer style; additional styles require an explicit future request.
