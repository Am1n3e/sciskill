---
layout: ../../layouts/DocLayout.astro
title: Rebuttal Desk
description: Review feedback, linked themes, proposed tasks, and response drafts in a local workspace.
eyebrow: Skills / Review & response planning
---

## Import and inspect reviews

Rebuttal Desk imports a rendered OpenReview HTML capture into YAML. It preserves reviewer IDs, section headings, original content, timestamps, and nested conversations. Its bundled browser viewer runs on a local Python server.

## Use with your agent

```text
/sciskill plan-rebuttal
```

Provide your initial reviews and submitted manuscript, including the appendix. Your agent imports the review content, analyzes it against the paper, and opens the resulting Rebuttal Desk view.

## Analyze and plan

The SciSkill `plan-rebuttal` workflow compares initial reviews with the manuscript and appendix. It annotates exact passages as clarifications or change requests, identifies existing evidence, clusters related concerns into themes, and proposes tasks for author approval.

Analysis opens with an overview and numbered themes. Reviews preserve the source text alongside annotated passages and draft panes. Tasks link proposed work to the concerns it addresses.

## Drafts and limits

Edit drafts in workspace Markdown files and use Reload to update the viewer. The final response combines nonempty drafts for each reviewer and shows word and character counts. A draft's presence does not prove that it answers the concern.

The tool does not generate experiments or results. OpenReview-style presentation does not guarantee exact OpenReview Markdown or mathematics rendering. Review the final response before submission.
