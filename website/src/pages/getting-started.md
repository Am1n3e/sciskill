---
layout: ../layouts/DocLayout.astro
title: Getting started
description: Add SciSkill to your agent, initialize your project, and choose a research task.
---

## Setup

```sh
npx skills add Am1n3e/sciskill
```

## Initialize your project

In your agent, run:

```text
/sciskill init
```

Provide your LaTeX and bibliography paths and an optional venue. Your agent initializes local configuration and storage. Your `.gitignore` stays unchanged unless you opt in.

## Check references

```text
/sciskill bib-lint references.bib
```

Use `paper.pdf` instead to audit a PDF's reference list. Your input stays unchanged.

Without an agent:

```sh
uvx sciskill bib-lint verify paper.pdf --output paper-audit --json
uvx sciskill bib-lint view paper-audit
```

[Follow the visual walkthrough](../tools/bib-lint/) for screenshots, expanded findings, BibTeX input, and rechecks.

## Plan your rebuttal

```text
/sciskill plan-rebuttal
```

Provide the initial reviews and submitted manuscript, including its appendix. Your agent identifies actionable passages, checks existing evidence, groups related concerns into themes, and proposes tasks in Rebuttal Desk. You review the proposed work and retain control of response drafts and manuscript changes.
