# Rebuttal task list — discussion draft

## Purpose

A researcher-maintained, paper-wide checklist of work arising from the reviews. Agent analysis can propose tasks later; the researcher decides what to undertake, prioritizes it, and tracks completion before submitting the rebuttal.

## Current data model

Each task represents a piece of work and can link to several annotation IDs across reviewers. One experiment can address multiple concerns; an annotation can also require multiple tasks.

Fields:

- `id`: stable task identifier.
- `title`: concrete work to perform.
- `annotations`: the source annotation IDs this work addresses.
- `status`: one field combining decision and progress: proposed, pending, in_progress, done, or not_doing.
- `priority`: high, medium, or low, editable by the researcher.
- `effort`: low, medium, or high; separate from priority.
- `note`: brief context or record of what was done, or why the task will not be done.
- `external_link`: optional URL to an externally tracked item, such as a GitHub issue. No external synchronization is implied.

Experimental work may need an early start because of lead time and dependencies. Effort alone should not determine importance. A small typo typically has low priority, while a critical short correction may deserve high priority.

## Open decisions

- Confirm task granularity and fields before implementation.
- Decide whether priority labels suffice or explicit manual ordering is needed.
- Decide the storage file after agreeing the model.
- Discuss presentation only after the data model is settled.

The initial read-only task view is implemented; automatic task generation and task editing in the browser have not been introduced.

## Agreed refinements

- Task IDs must be unique.
- Keep `annotations` as the links back to relevant review passages for now.
- Combine decision and progress into one `status`; no separate decision field.
- Rename completion_note to singular `note`.
- Keep effort and priority separate.
- Use proposed, pending, in_progress, done, and not_doing in the proposal.
- Add an optional external_link for externally tracked work.

## Proposed status meanings

| Value | Meaning |
| --- | --- |
| `proposed` | Agent-proposed work awaiting the researcher's decision |
| `pending` | Researcher accepted the task; work has not started |
| `in_progress` | Work has started |
| `done` | Work is complete |
| `not_doing` | Explicit decision not to undertake it |

The researcher moves a proposed task to pending when accepting it, or to not_doing when declining it. Accepted work moves from pending to in_progress to done. There is no deferred status.

## Current example

```yaml
tasks:
  - id: 1
    title: Verify hardware-compatible sparsity
    annotations: [GruC-C3, GruC-C9]
    status: proposed
    priority: high
    effort: high
    note: ""
    external_link: null
```

## Implemented presentation

- Title above top-level Reviews and Tasks tabs.
- Reviewer picker is inside Reviews.
- Tasks has an independent reviewer filter, defaulting to All reviewers.
- Each task appears once even when it links to several reviewers; filtering matches any linked reviewer.
- Tasks are read from a top-level `tasks` list in workspace.yaml (optional, default empty). No external tracking synchronization or browser editing added.
- Table shows title/annotation links/note/external link, status, priority, and effort. Highest priority is shown first, with file order retained for ties.
- Current research example has no tasks yet; task proposals will come with the later analysis step.

## Sample tasks for UI review

At the user's request, populated the ignored local example workspace with seven sample proposed tasks grounded in Reviewer GruC's annotations. Tasks cover hardware-compatible sparsity, reconciling baseline numbers, alternative criteria, an attention extension, contribution clarification, related work, and code release. All are proposed; priority/effort values are illustrative, not researcher-approved decisions. No external issue was created or linked.

Task IDs are stored as unique positive integers (1, 2, 3), not prefixed strings. UI labels and theme task references use the stored ID.
