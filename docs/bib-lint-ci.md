# Check references added by a pull request

SciSkill 0.3.0 adds Git selection to the existing bibliography verifier:

```sh
git fetch origin main
uvx sciskill bib-lint verify references.bib --base origin/main \
  --output .out/bib-lint --fail-on-invalid --json
```

`--base REF` compares the committed `--head` (default `HEAD`) with its Git merge
base with `REF`. Only keys absent from all tracked `.bib` files at that merge base
are audited in the selected head bibliography. Matching is case-insensitive;
formatting changes, edited existing entries, moved entries, and deletions do not
trigger lookups. A renamed citation key counts as new. Uncommitted edits are not
part of the comparison. Both revisions and their history must be available locally.

BibTeX is parsed at both revisions, including string macros. Missing revisions,
malformed bibliographies, untracked head inputs, and bibliography symlinks are
errors, never treated as an empty baseline. Git selection accepts `.bib` input and
cannot be combined with `--aux`. Use a fresh output directory for a different Git
comparison; saved audits record and bind the base, merge base, head, path, and keys.
The report contains only selected entries and leaves citation usage unknown.
No new keys produce a completed empty report without source requests.

`--fail-on-invalid` is opt-in: exit 1 means a confirmed invalid reference; exit 2
means an input or operational error; interruption returns 130. Valid and unresolved
completed audits return 0. Unresolved, partial-match, and needs-review findings
require inspection and are not evidence that a reference is invalid. Without this
flag, existing verifier exit behavior is unchanged.

## GitHub Actions

Add this PR-only job to the paper's Checks workflow. It needs no write token,
API secrets, or Docker. The Action writes a step summary with one result per new
reference. Upload the output directory to retain source comparisons and evidence.

```yaml
  references:
    name: Check new references
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false
      - uses: Am1n3e/sciskill/actions/bib-lint@v0.3.0
        with:
          path: references.bib
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
      - name: Upload new-reference audit
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: new-references-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
          path: .out/bib-lint/
          include-hidden-files: true
          retention-days: 14
```

The Action accepts `path` (default `references.bib`), required `base`, `head`
(default `HEAD`), `output` (default `.out/bib-lint`), and the pinned package
`version` (default `0.3.0`). Use `pull_request` with read-only permissions.
The summary escapes citation keys and distinguishes unresolved findings from
invalid ones. The Action preserves the verifier's exit code, so invalid references
fail the job while a source outage remains an unresolved finding in the report.
