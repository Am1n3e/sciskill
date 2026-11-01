# Changelog

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
