---
layout: ../layouts/DocLayout.astro
title: Getting started
description: Run the tools locally or add the rebuttal-analysis skill to your agent.
---

## Run from source

Install [uv](https://docs.astral.sh/uv/), then clone the repository. Python 3.12 or newer is required.

```sh
git clone https://github.com/Am1n3e/sciskill.git
cd sciskill
uvx --from . sciskill --help
```

## Check references

```sh
uvx --from . sciskill bib-lint verify references.bib
uvx --from . sciskill bib-lint view references.bib-lint
```

Add `--aux paper.aux` to verify only cited references. Without it, all entries are checked. Sources are never edited. Failed lookups require review and do not establish that a citation is wrong.

## Open a rebuttal workspace

Save the rendered OpenReview discussion after its reviews and replies have loaded, then import it:

```sh
uvx --from . sciskill rebuttal import-openreview discussion.html my-rebuttal
uvx --from . sciskill rebuttal view my-rebuttal
```

The importer preserves review content and conversations in YAML. It does not generate analysis or drafts. Workspace files remain local; Reload rereads changes made in your editor.

## Add the agent skill

```sh
npx skills add Am1n3e/sciskill
```

Use the `plan-rebuttal` workflow with the initial reviews and submitted manuscript, including its appendix. It produces annotated concerns, cross-review themes, and proposed tasks. Authors review the proposed work and retain control of response drafts and manuscript changes.
