# bib-lint

Audit local BibTeX metadata against independent scholarly sources, then inspect
comparisons and raw evidence in a local UI. Source bibliographies and compiled AUX
files are never edited. Requires Python 3.12+ and macOS/Linux.

Verification preserves structured author names and checks every supplied scholarly
locator, including secondary aliases and version pins. Conflicting `journal` and
`booktitle` fields, malformed locators, and unverified secondary identifiers remain
visible as findings. Local contradictions still require review when sources are
unavailable. Metadata checks do not assess scientific claim support, pages, volume,
or edition.

Run with UVX, which keeps tool dependencies outside your paper's environment:

```sh
uvx sciskill bib-lint verify /path/to/references.bib --aux /path/to/paper.aux
uvx sciskill bib-lint view /path/to/references.bib-lint
```

Without `--aux`, verification checks all entries and leaves citation usage unknown.
The default audit directory is `<input-stem>.bib-lint` beside the input. It contains
the report, resumable checkpoint, and integrity-checked cached evidence. Use
`--output DIRECTORY` to select another location and `--json` for a structured final
result; check its `status` and `complete` fields for partial or interrupted runs.
Repeating the verification command resumes unfinished work and preserves saved outcomes,
including source failures. Use `--refresh` to retry failures (`--key KEY` limits the
recheck to one reference). `--refresh` fetches
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

For source development and checks, see [Contributing](../../CONTRIBUTING.md).

The adversarial bibliography has independent expectations and fixed public-paper
metadata excerpts. From `tools/bib-lint`, run its deterministic audit with:

```sh
PYTHONPATH=src uv run --group dev python -m evaluation.adversarial --output ../../.local/bib-lint-adversarial
```

This command checks both all-source and focused-provider outcomes, plus citation-key
and AUX invariants. It exits with status 1 if any challenge expectation remains unmet.
