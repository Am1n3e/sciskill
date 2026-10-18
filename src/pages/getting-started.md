---
layout: ../layouts/DocLayout.astro
title: Getting started
description: Start with the tools that exist today. Add agent skills as they become available.
---

## What you can use today

Science Skills is a collection in development. **bib-lint has public source and can run locally. Rebuttal Desk is a local prototype. The reusable agent skills have not been released yet.** There is no collection-wide installer or supported slash-command set at this stage.

The website is a catalog and field guide. Your bibliography, manuscripts, and reviews are processed by the local tools, not by this website.

## Set up bib-lint

You need Git, Python 3.12 or later, and [uv](https://docs.astral.sh/uv/). The current tool supports macOS and Linux.

```sh
git clone https://github.com/Am1n3e/bib-lint.git
cd bib-lint
uv sync --locked
uv run bib-lint --help
```

The help output is the source of truth for the commands supported by the checked-out version. The [public repository](https://github.com/Am1n3e/bib-lint) contains the implementation, tests, and benchmark harness.

## Run an audit

Verify a bibliography against scholarly sources, then open its report:

```sh
uv run bib-lint verify references.bib
uv run bib-lint view references.bib-lint
```

Source bibliographies and compiled AUX files are not edited. An audit can contact external scholarly providers; their availability affects coverage.

## Review the result

Inspect the finding, the retrieved record, and the comparison. Distinguish a demonstrated mismatch from an unresolved lookup. A source outage does not establish that a citation is wrong.

## Rebuttal Desk

The viewer currently lives in a paper-specific local workspace. A reusable package and public installation instructions are not available yet. Its planned agent skills will help extract concerns, plan responses, and assess response coverage, with the author reviewing decisions.

## What comes next

Each released skill should include its trigger, inputs, procedure, expected outputs, and limitations. It should also declare what has actually been evaluated. Compatibility and performance claims will follow testing, rather than precede it.
