# SciSkill

**Agent skills and tools for scientists.**

Keep your focus on the science. Let your agent handle the grunt work.

![A scientist writes Transformer equations while a small robot sweeps up chalk dust](website/public/images/scientist-robot-transformer.png)

## Setup

```sh
npx skills add Am1n3e/sciskill
```

## Usage

```text
/sciskill init
```

Initialize `.sciskill/` with your LaTeX and bibliography paths, optional venue, and local cache storage. Your `.gitignore` stays unchanged unless you opt in.

```text
/sciskill bib-lint
```

Check bibliography metadata against scholarly records and inspect the findings and source evidence.

```text
/sciskill plan-rebuttal
```

Analyze initial reviews against your submitted manuscript and appendix. Annotate actionable passages, group related concerns into themes, and propose tasks for your review. You retain control of response drafts and manuscript changes.

## Tools

SciSkill pairs agent instructions with tools that carry out the work and make the results easy to inspect. Agents can use these tools as part of a skill, and you can also run them directly.

### bib-lint

Check bibliography metadata against scholarly sources and inspect findings alongside their evidence in a local viewer. See [bib-lint](tools/bib-lint/README.md).

```sh
uvx sciskill bib-lint --help
```

### Rebuttal Desk

Import OpenReview discussions and view reviews, linked themes, tasks, and response drafts in a local workspace. See [Rebuttal Desk](tools/rebuttal-desk/README.md).

```sh
uvx sciskill rebuttal --help
```

## Citation

```bibtex
@misc{elhattami2026sciskill,
  author = {El Hattami, Amine},
  title = {{SciSkill}: Agent skills and tools for scientists},
  year = {2026},
  url = {https://github.com/Am1n3e/sciskill}
}
```
