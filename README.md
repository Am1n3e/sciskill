# SciSkill

Agent tools and skills for scientists: bibliography audits with bib-lint and review-response workspaces with Rebuttal Desk.

## Run the tools

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. From this checkout:

```sh
uvx --from . sciskill --help
uvx --from . sciskill bib-lint verify /path/to/references.bib
uvx --from . sciskill bib-lint view /path/to/references.bib-lint
uvx --from . sciskill rebuttal import-openreview /path/to/discussion.html /path/to/my-rebuttal
uvx --from . sciskill rebuttal view /path/to/my-rebuttal
```

Both tools and their browser assets are bundled. Dependencies stay outside your paper's environment. After an alpha is published to PyPI, use `uvx --prerelease allow sciskill` in place of `uvx --from . sciskill`.

See [bib-lint](tools/bib-lint/README.md) and [Rebuttal Desk](tools/rebuttal-desk/README.md) for inputs, outputs, and limitations.

## Agent skill

```sh
npx skills add Am1n3e/sciskill
```

The [SciSkill instructions](skills/sciskill/SKILL.md) define the `plan-rebuttal` workflow: analyze initial reviews against the manuscript, annotate actionable passages, and produce linked themes and proposed tasks. The author reviews decisions and writes the response drafts.

## Repository structure

- `website/`: Astro site, static assets, and configuration.
- `tools/bib-lint/`: bibliography audit engine and local browser viewer.
- `tools/rebuttal-desk/`: OpenReview importer and local review workspace viewer.
- `tools/sciskill/`: shared command launcher and package integration tests.
- `skills/`: agent instructions and supporting references.

Research workspaces, captured reviews, audit reports, screenshots, and generated build files are excluded from Git.

## Checks

```sh
python3 -m unittest discover -s tools/sciskill/tests -v
uv run --project tools/rebuttal-desk python -m unittest discover -s tools/rebuttal-desk/tests -v
cd tools/bib-lint
uv run --group dev pytest -q -m 'not package'
```

## Website

Requires Node.js 22.22.0 or newer:

```sh
cd website
npm ci
npm run dev
npm run check
npm run build
```

The site uses `/sciskill/` as its base path. The Pages workflow builds pull requests and deploys `main` when GitHub Pages is configured to use GitHub Actions.

## Publishing

Publish a GitHub release with a tag matching `v<version>` from `pyproject.toml`, currently `v0.1.0a1`. The [publish workflow](.github/workflows/publish.yml) tests the installed tools and both viewers, builds and validates the distributions, and uploads them to PyPI with Trusted Publishing.

The PyPI publisher must match owner `Am1n3e`, repository `sciskill`, workflow `publish.yml`, and environment `pypi`. No API token is needed.

## License

The site template was modified on 18 October 2026. Licensed under [GPL-3.0](LICENSE).
