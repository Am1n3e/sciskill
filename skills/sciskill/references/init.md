# Initialize

Create `.sciskill/config.yaml` for project paths and the optional venue, plus `cache/` and `tmp/` directories for local artifacts. Existing settings and artifacts are preserved.

1. Work from the user's project root. Use supplied paths or existing configuration; ask for missing LaTeX and bibliography paths or an ambiguous choice. The LaTeX path can be a file or directory. Venue is optional.
2. Run the command with the available inputs. Omit unspecified flags. Add `--update-gitignore` only when the user opts in; the default leaves `.gitignore` untouched.

   ```sh
   uvx sciskill init --latex paper.tex --bib references.bib --venue NeurIPS
   ```

   If uv is unavailable, use the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/) within the environment's permissions.
3. On success, read `.sciskill/config.yaml` and confirm the stored paths, venue, and whether `.gitignore` changed. On failure, report the error instead of claiming initialization succeeded.
