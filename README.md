# Science Skills

Agent tools and skills for scientists.

This is the local catalog-site preview for bib-lint and Rebuttal Desk. It uses Astro, Markdown pages, and a static GitHub Pages deployment workflow. Existing tool availability and planned agent skills are identified separately.

## Local development

Requires Node.js 22.22.0 or newer.

```sh
npm ci
npm run dev
```

The site uses the `/science-skills/` base path in local development and production. Open the local URL printed by Astro with that path.

```sh
npm run check
npm run build
npm run preview
```

## GitHub Pages

The included workflow checks and builds pull requests. Pushes to `main` and manual runs on `main` also deploy the build to the `github-pages` environment.

To publish, create the intended collection repository and choose **GitHub Actions** under **Settings → Pages → Build and deployment → Source**. Confirm the owner and repository name match `site` and `base` in `astro.config.mjs` before enabling deployment. No live repository or deployment is created by this local preview.

The current proposed target is `Am1n3e/science-skills`. If the repository name or domain changes, update the Astro configuration. All internal navigation and local assets derive their URLs from Astro's base URL.

## Content

- `src/pages/index.astro`: catalog homepage and illustrative interactive examples.
- `src/pages/*.md`: general documentation.
- `src/pages/tools/*.md`: capability pages.
- `src/layouts/`: shared navigation and documentation layout.
- `src/styles/global.css`: responsive visual system.

All demo citations and review passages on the homepage are illustrative. No real manuscript or reviewer content is included.
