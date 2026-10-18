# Initialize a SciSkill project

Use `/sciskill init` to prepare the project's local configuration and storage. The agent calls the real `sciskill init` terminal command. This does not create a Rebuttal Desk workspace.

## Establish the project and inputs

Use the user's project directory as the working directory. Obtain the LaTeX source path (file or directory), bibliography file path, and optional venue from the user or unambiguous project context. Do not guess between multiple manuscripts or bibliographies. Paths can be supplied later; omitted values remain unset on first initialization and retain their existing values on subsequent runs.

The command stores configuration in `.sciskill/config.yaml` and creates `.sciskill/cache/` and `.sciskill/tmp/` for cache data and temporary artifacts. It stores paths relative to the project root. Manuscripts, bibliographies, existing cache files, and other configuration values are preserved.

Updating `.gitignore` is opt-in and defaults to off. Pass `--update-gitignore` only if the user explicitly requests it; otherwise leave that file untouched. Do not add repository rules, modify shell profiles, or install dependencies into the project's Python environment.

## Run initialization

Ensure `uv` and `uvx` are available, reusing an existing working installation. If uv is missing, use a suitable method from the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/), subject to the environment's permissions. Do not upgrade a working installation just for initialization.

From the project directory, pass the available inputs:

```sh
uvx --prerelease allow sciskill init --latex paper.tex --bib references.bib --venue NeurIPS
```

Omit flags for unspecified values. Use `--update-gitignore` only on explicit opt-in; `--no-update-gitignore` is also accepted. No repository checkout, `pip install`, or `uv sync` is needed. UVX manages the published tools and their dependencies outside the project environment.

Stop if initialization fails and report the reason; do not overwrite malformed configuration or silently switch to another package. Inspect the resulting YAML and confirm the paths and venue. Report whether `.gitignore` was changed. Do not run audits, import reviews, delete caches, launch servers, or open browsers as part of init.
