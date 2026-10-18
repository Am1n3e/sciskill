---
layout: ../../layouts/DocLayout.astro
title: Rebuttal Desk
description: A local workbench for reviewer concerns, analysis, and response drafts—with the author making the decisions.
eyebrow: Skills / Review & response planning
---

**Availability: paper-specific local prototype. Reusable agent skills: planned.**

## What already works

The existing HTML viewer preserves original review text and links concern-level workbenches to analysis and response drafts. It connects related concerns, renders Markdown and mathematics, and assembles a response with word and character counts.

The current viewer is customized to one research workspace. It has not yet been packaged as a general-purpose public release.

## What the skill layer would add

The proposed workflow takes reviewer feedback, the paper, available evidence, and an optional response draft. It would help:

1. Extract explicit questions and substantive concerns, preserving their source passages.
2. Connect overlapping requests across reviewers without losing their original context.
3. Propose a response action: clarify, provide evidence, run an experiment, acknowledge a limitation, or combine duplicates.
4. Map draft responses back to concerns and identify missing evidence or unanswered parts.

Each proposed action should carry a rationale. The author reviews decisions to combine, defer, or omit a concern.

## Example: a concern becomes a plan

This is illustrative, not an analysis from a real submitted paper.

> “The ablation does not isolate the contribution of retrieval quality.”

A useful plan would identify the requested comparison, locate any existing evidence, and mark a new ablation as a decision for the author. It would not invent an experiment or report a result that was never measured.

## What “addressed” currently means

The viewer's addressed counter detects a filled response rather than a blank or placeholder. **It does not assess whether the answer resolves the concern.** Semantic coverage checking is a proposed capability that still needs implementation and evaluation.

## Availability and evaluation

There is no public installation package or hosted review-processing service yet. This catalog does not publish private manuscript or review content. The analysis skills have no task-level evaluation results at this stage.
