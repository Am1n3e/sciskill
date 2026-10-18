# bib-lint

Audit local BibTeX metadata against independent scholarly sources, then inspect
comparisons and raw evidence in a local UI. Source bibliographies and compiled AUX
files are never edited. Requires Python 3.12+ and macOS/Linux.

From the collection repository root, run `uvx --from . sciskill bib-lint` followed by the action and arguments. The commands below also work from this tool directory.

Run from this tool directory with UVX, which keeps tool dependencies outside your
paper's environment:

```sh
uvx --from . bib-lint verify /path/to/references.bib --aux /path/to/paper.aux
uvx --from . bib-lint view /path/to/references.bib-lint
```

Without `--aux`, verification checks all entries and leaves citation usage unknown.
The default audit directory is `<input-stem>.bib-lint` beside the input. It contains
the report, resumable checkpoint, and integrity-checked cached evidence. Use
`--output DIRECTORY` to select another location and `--json` for a structured final
result; check its `status` and `complete` fields for partial or interrupted runs.
Repeating the verification command resumes eligible work; `--refresh` fetches
selected evidence again.

`bib-lint view` also starts without a path. Its local browser interface can parse,
verify, open, stop, and resume audits. Reload rereads saved results; Recheck sources
performs new lookups. The interface uses a loopback Python server and bundled
HTML/CSS/JavaScript with no frontend installation. Use `--port PORT` or
`--no-browser` when needed.

Agent assessments are read separately from `report.agent.json` inside an audit
directory (or `<report-stem>.agent.json` for a report file). They are bound to exact
entry hashes and never replace automated consensus. Evidence paths can be selected
in Audit setup. The browser displays comparisons, proposed corrections, primary
source links, and checksum-verified cached responses; it does not edit the
bibliography.

For an installed command, use `uv tool install .` (or `uv tool install --editable .`
for development), or install a built wheel from `uv build`. This is separate from
development dependency setup with `uv sync --group dev`.
