# Contributing

## Repository structure

- `website/`: Astro site, static assets, and configuration.
- `tools/bib-lint/`: bibliography audit engine and local browser viewer.
- `tools/rebuttal-desk/`: OpenReview importer and local review workspace viewer.
- `tools/sciskill/`: shared command launcher and package integration tests.
- `skills/`: agent instructions and supporting references.

Research workspaces, captured reviews, audit reports, screenshots, and generated build files are excluded from Git.

## Checks

```sh
uv run --no-project --with 'PyYAML>=6,<7' python -m unittest discover -s tools/sciskill/tests -v
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

Publish a GitHub release with a tag matching `v<version>` from `pyproject.toml`, currently `v0.1.0`. The [publish workflow](.github/workflows/publish.yml) tests the installed tools and both viewers, builds and validates the distributions, and uploads them to PyPI with Trusted Publishing.

The PyPI publisher must match owner `Am1n3e`, repository `sciskill`, workflow `publish.yml`, and environment `pypi`. No API token is needed.

