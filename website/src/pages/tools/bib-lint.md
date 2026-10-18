---
layout: ../../layouts/DocLayout.astro
title: bib-lint
description: Audit local BibTeX metadata against scholarly sources, then inspect the comparisons and raw evidence.
eyebrow: Skills / Reference auditing
---

## When to use it

Use bib-lint when you want to check whether citation metadata matches an independently retrieved scholarly record. It checks core fields such as title, authors, year, venue, DOI, and arXiv identifiers against applicable built-in providers.

## Inputs

- A local BibTeX bibliography or a previously generated report.
- An optional compiled AUX file for determining which bibliography entries were cited.
- Network access to the applicable scholarly providers during verification.

The bibliography and AUX files are read without editing their contents.

## What you get

- A structured report with reference-level decisions and field comparisons.
- Saved lookup evidence and provider errors.
- A local viewer for examining the report and supporting evidence.

## How to read a finding

A report can distinguish a confirmed match, a demonstrated discrepancy, and a reference that remains unresolved or needs review. Index agreement is supporting evidence; it does not replace an authoritative record.

> A failed search is a limitation of the lookup. It is not proof that the cited publication does not exist.

## Evaluation

The repository includes a harness for HALLMARK, a manually verified Zenodo citation dataset, and the GPTZero and HalluCitation reported-positive collections. These protocols measure different things. Positive-only detection coverage cannot establish false-positive performance.

Current and previous benchmark runs must be interpreted alongside evaluated coverage, definitive answers, source errors, and the recorded code and input identities. No aggregate performance claim is made.

## Boundaries

The audit concerns core citation metadata. It does not establish whether a paper supports a manuscript's claim, and does not fully verify pages, volume, edition, or every publication domain. Provider coverage, citation formatting, and publication-version differences can require human review.

## Use the tool

Run the SciSkill bibliography tool:

```sh
uvx sciskill bib-lint verify references.bib
uvx sciskill bib-lint view references.bib-lint
```

The viewer is bundled HTML, CSS, and JavaScript served locally by Python. It can start audits, open saved reports, inspect evidence, and stop or resume runs. Source bibliographies are not modified.
