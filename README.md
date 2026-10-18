# SciSkill

**Agent skills and tools for scientists.**

Keep your focus on the science. Let your agent handle the grunt work.

![A scientist writes Transformer equations while a small robot sweeps up chalk dust](website/public/images/scientist-robot-transformer.png)

## Setup

Use an agent that supports skills. Install [uv](https://docs.astral.sh/uv/) for the tools and Node.js with npm for the skill installer. The tools require Python 3.12 or newer.

Add SciSkill to your agent:

```sh
npx skills add Am1n3e/sciskill
```

## Use with your agent

Ask your agent to use SciSkill's `plan-rebuttal` workflow and provide the initial reviews, submitted manuscript, and appendix. The agent analyzes reviewer requests against the paper, annotates actionable passages, and produces linked themes and proposed tasks for Rebuttal Desk.

You review the proposed work and write the response drafts. See the [SciSkill instructions](skills/sciskill/SKILL.md) for the analysis workflow.

## Run tools directly

To run without an agent, use the published [SciSkill package from PyPI](https://pypi.org/project/sciskill/):

```sh
uvx --prerelease allow sciskill --help
uvx --prerelease allow sciskill bib-lint verify /path/to/references.bib
uvx --prerelease allow sciskill bib-lint view /path/to/references.bib-lint
uvx --prerelease allow sciskill rebuttal import-openreview /path/to/discussion.html /path/to/my-rebuttal
uvx --prerelease allow sciskill rebuttal view /path/to/my-rebuttal
```

Both tools and their browser assets are bundled. Dependencies stay outside your paper's environment; no repository checkout is needed. The prerelease flag selects the alpha release.

See [bib-lint](tools/bib-lint/README.md) and [Rebuttal Desk](tools/rebuttal-desk/README.md) for inputs, outputs, and limitations.

For repository development, checks, website setup, and release instructions, see [Contributing](CONTRIBUTING.md).
