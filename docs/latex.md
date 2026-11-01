# LaTeX commands and GitHub Actions

Requires [uv](https://docs.astral.sh/uv/) and a running Docker engine on macOS or Linux. SciSkill uses a pinned [TeX Live image](https://github.com/xu-cheng/latex-docker), including latexmk, pdfLaTeX, BibTeX, ChkTeX, Java, and latexdiff. A native LaTeX installation is unnecessary.

## Commands

```sh
uvx sciskill latex-build
uvx sciskill latex-clean
uvx sciskill latex-lint
uvx sciskill latex-spell
uvx sciskill latex-diff --base origin/main
```

Commands use `main.tex`, or the `latex` path in `.sciskill/config.yaml` if initialized. Override with `--main paper.tex` and select a project with `--root path/to/paper`. Relative includes resolve from the main file's directory. Generated files stay in that directory's `.out/`; `latex-clean` removes that directory. Keep source assets outside `.out/` and add it to `.gitignore`.

Compilation mounts source files read-only, disables container networking, and uses a writable output directory. SciSkill supplies defaults; a paper's `.latexmkrc` and `.chktexrc` take precedence. Builds use `.out/` even with a project latexmk configuration. TeX configuration files are executable code; build repositories you trust.

Spelling checks use checksum-verified [TeXtidote 0.9](https://github.com/sylvainhalle/textidote). Only US-English spelling findings fail the check. Sources default to `content/**/*.tex`, or the main document with included files if no content directory is present. Pass source paths explicitly to select other sections. A project's `.textidote` supplies its policy; otherwise defaults and an optional `spelling.txt` vocabulary apply. The complete report is written to `.out/spell.log`.

Diffs compare the committed `--head` (default `HEAD`) against its merge base with `--base` (default `origin/main`). Both revisions must be available locally. SciSkill builds both snapshots, flattens included sections and generated bibliographies with latexdiff, then compiles `.out/paper-diff.pdf` and `.out/paper.pdf`. Changed image pixels may not be highlighted. Failed builds retain intermediate logs under `.out/paper-diff-*/`. Git snapshots containing symlinks are rejected.

## GitHub Actions

After checking out your paper, run a command with:

```yaml
- uses: Am1n3e/sciskill/actions/latex@v0.2.0
  with:
    command: build
```

`command` accepts `build`, `clean`, `lint`, `spell`, or `diff`. Optional inputs are `root`, `main`, `version` (SciSkill package version), and `base`/`head` for diffs. Use separate jobs or workflows for compilation and checks. GitHub-hosted Ubuntu runners provide Docker.

For PR diffs, checkout the PR head with `fetch-depth: 0` and `persist-credentials: false`. Run the diff Action in a job with only `contents: read`, passing the PR base and head SHAs. Filter the `pull_request` event to manuscript, bibliography, styles, figures, and build configuration paths.

Upload the two PDFs using `actions/upload-artifact` with these names and 30-day retention:

| File | Artifact name |
| --- | --- |
| `.out/paper-diff.pdf` | `paper-diff-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}` |
| `.out/paper.pdf` | `paper-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}` |

Enable `include-hidden-files: true` when uploading `.out/` files.

Publish their links from a **separate trusted workflow**:

```yaml
name: Publish paper preview
on:
  workflow_run:
    workflows: [Paper diff]
    types: [completed]
permissions:
  actions: write
  pull-requests: write
concurrency:
  group: paper-preview-${{ github.event.workflow_run.head_repository.id || github.repository_id }}-${{ github.event.workflow_run.head_branch }}
  cancel-in-progress: false
jobs:
  comment:
    if: github.event.workflow_run.event == 'pull_request'
    runs-on: ubuntu-24.04
    steps:
      - uses: Am1n3e/sciskill/actions/paper-preview@paper-preview-v0.3.0
```

The default expected build workflow path is `.github/workflows/paper-diff.yml`; set the publisher's `workflow` input if yours differs. The publisher reads GitHub metadata, verifies the run and current PR head, and creates or updates its own preview comment. It never executes PR code or downloads artifacts. Keep the publishing workflow on the default branch and never pass its write token to the PR build. Version 0.3.0 requires `actions: write` so a build finishing after merge can remove its late uploads.

Comments use `github-actions[bot]` with the default token. A custom SciSkill identity requires a GitHub App installation token supplied as `github-token`, plus its login (such as `sciskill[bot]`) as `bot-login`. An Action's display name does not change the comment author. Existing comments retain their original author.

## Retention and merge cleanup

Set the `PAPER_PREVIEW_RETENTION_DAYS` repository Actions variable to choose PDF retention. A paper-diff workflow can use one shared value for both upload steps:

```yaml
env:
  PAPER_PREVIEW_RETENTION_DAYS: ${{ vars.PAPER_PREVIEW_RETENTION_DAYS || '30' }}
# In each PDF upload step:
# with:
#   retention-days: ${{ env.PAPER_PREVIEW_RETENTION_DAYS }}
```

The value must fit the repository's artifact retention limits. The comment displays the earlier PDF expiry reported by GitHub, in UTC. Repository variables affect subsequent uploads.

Add a trusted cleanup workflow on the default branch:

```yaml
name: Remove merged paper previews
on:
  pull_request_target:
    types: [closed]
  workflow_dispatch:
    inputs:
      pull-request:
        description: Merged PR number to clean up
        required: true
        type: number
permissions:
  actions: write
  pull-requests: write
concurrency:
  group: paper-preview-${{ github.event.pull_request.head.repo.id || github.repository_id }}-${{ github.event.pull_request.head.ref || format('pr-{0}', inputs.pull-request) }}
  cancel-in-progress: false
jobs:
  cleanup:
    if: github.event_name == 'workflow_dispatch' || github.event.pull_request.merged == true
    runs-on: ubuntu-24.04
    steps:
      - uses: Am1n3e/sciskill/actions/paper-preview@paper-preview-v0.3.0
        with:
          mode: cleanup
          pull-request: ${{ inputs.pull-request }}
```

Cleanup verifies the merged PR through GitHub, then deletes its `paper-pr-<number>-<sha>` and `paper-diff-pr-<number>-<sha>` artifacts across revisions. Each artifact's workflow, repository, PR association and commit must match. Logs, workflow runs and unrelated artifacts remain available. The bot updates its existing preview comment to **“PR merged — preview PDFs removed”** and links to the PR checks.

The shared concurrency group serializes automatic publication and merge cleanup. Publication also cleans artifacts uploaded after merge. Manual cleanup can remove older merged PR previews; open PRs and PRs closed without merging are left alone. This workflow requires no checkout of PR code.
