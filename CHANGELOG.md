# Changelog

## Paper preview Action 0.3.0

### Added

- Merge cleanup removes verified preview PDFs across PR revisions and updates the existing bot comment while preserving workflow logs and checks.
- Late builds also clean their uploads after merge; manual cleanup supports older merged PRs.

### Changed

- Comments display the actual PDF expiry reported by GitHub instead of a fixed duration.
- The trusted publisher now requires `actions: write` for late-upload cleanup. Use `Am1n3e/sciskill/actions/paper-preview@paper-preview-v0.3.0` with the cleanup workflow in the LaTeX guide. The Python package and LaTeX Action remain at 0.2.0.

## Paper preview Action 0.2.1

### Changed

- Explain the highlighted and clean PDFs in a review table, with build metadata in a compact footer.
- Distinguish ready, unavailable, and failed PDF previews.

Use `Am1n3e/sciskill/actions/paper-preview@paper-preview-v0.2.1`. The Python package and LaTeX Action remain at 0.2.0.

## 0.2.0

### Added

- `latex-build`, `latex-clean`, `latex-lint`, `latex-spell`, and `latex-diff` commands, usable directly through `uvx sciskill` without a repository-local task runner.
- Tagged GitHub Actions for LaTeX commands and PR preview comments, with optional GitHub App token support.
- Installed-package acceptance checks covering actual LaTeX compilation, spelling failures, and rendered manuscript diffs.
