---
layout: ../layouts/DocLayout.astro
title: Evaluation & limitations
description: What the tools check, what the scores mean, and what has not been demonstrated yet.
---

## Tool tests and skill evaluations answer different questions

A deterministic test can establish that parsing, checkpointing, or a report contract behaves as expected. A benchmark measures behavior under a particular dataset and scoring protocol. An agent-skill evaluation should separately ask whether the procedure improves the same agent's performance over using the tools without the skill.

None of these is interchangeable with the others.

## What is checked

bib-lint includes parsing, verification, cache-integrity, job, CLI, and viewer tests plus a citation benchmark harness. Rebuttal Desk tests workspace validation, source integrity, imports, and rendering. The shared package has isolated installation and browser-server tests.

These checks establish software behavior. They do not establish the correctness of an agent's scientific analysis or guarantee that a response resolves a reviewer's concern.

## Read citation benchmarks with their denominator

HALLMARK's public development and test splits include both valid and problematic references. They can measure false positives as well as detection. Its stress test and the GPTZero and HalluCitation collections are positive-only after the harness excludes the canary, so detection rates do not establish performance on valid citations.

The manually verified Zenodo dataset contains both classes, but is small. Raw-citation adapters can fail before the verification engine runs, which must be reported as an input or conversion failure rather than a successful classification.

Always inspect attempted, evaluated, and definitive coverage. A completed run can still contain unavailable sources or unevaluated cases. Uncertain answers are treated differently by different scoring protocols.

## What we want to measure for skills

- Whether the agent selects the right workflow for the task.
- Whether it preserves source evidence and distinguishes observations from inferences.
- Whether findings and planned actions are correct, not merely well formatted.
- Whether performance improves against an agent using the same tools without the skill, with comparable model and resource budgets.
- Whether it handles uncertainty and leaves the intended decisions with the researcher.

These are evaluation goals, not claimed results. A workflow being present in the catalog is not a certification of scientific correctness.
