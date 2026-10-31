# Implementation plan: locator-first provider queues

Status: In progress. Tasks and verification evidence are in [todo.md](todo.md).

## Goal

Use embedded Huey/SQLite queues for the shared PDF/BibTeX audit. Resolve supplied
paper URLs, then supported provider identifiers, before discovery. A resolved
locator is compared against the original citation and stops additional searches,
including when that comparison demonstrates an error. Preserve source evidence,
input contradictions, PDF uncertainty, workspace locking, and resumability.

## Decisions

- One Huey queue and worker per provider per audit; no custom worker loop or daemon.
- Shared provider execution locks and persisted pacing prevent simultaneous audits
  on the same machine from multiplying provider traffic. All waits are cancellable.
- One coordinator owns report mutations, progress callbacks and atomic checkpoints.
- Checkpoints are recovery truth. On restart, discard orphaned queue/schedule work
  and reconstruct only unfinished lookups. In-flight tasks lost by Huey are retried
  through this reconciliation, with cached successful responses reusable.
- Locators are retrieval hints, not trusted metadata. Compare retrieved fields with
  the untouched input. Unverified secondary identifiers and PDF evidence still gate
  Correct. A successful direct lookup does not imply multi-source consensus.
- Without a resolved locator, retain the existing independent source checks. They
  are ordered within a reference, while different references advance independently
  through provider queues. This preserves conflicting-source detection in fallback.
- Keep provider adapters synchronous. Separate retrieval queries from comparison;
  do not add a second matching or verdict implementation.
- Huey owns whole-lookup retries. Disable nested HTTP retries for queued execution,
  retain a total HTTP-attempt budget across scheduled retries, and persist provider
  cooldowns across references. Legacy standalone HTTP behavior remains supported.
- Resolve DOI redirects only through known resolver hosts, handing a recognized
  destination to its own provider queue. Unsupported publisher sites remain
  unverified and use normal fallback; never fetch arbitrary redirect destinations.
- Promote Huey to runtime dependencies in both installable distributions. Replace
  the prototype implementation with the production components rather than retain
  two schedulers or two verdict policies.

## Ordered tasks

1. Production queue runtime and dependency promotion.
2. URL/provider-identifier routing and shared direct comparison.
3. Cancellable provider locks, pacing, cooldowns and bounded retries.
4. Report checkpoint/resume integration for PDF and BibTeX.
5. DOI redirect routing and direct PDF URL normalization.
6. CLI/viewer/package acceptance and source-error regressions.
7. Correctness review, simplification, documentation and final verification.

Each task uses failing behavioral tests before its implementation. Existing source
checks are retained; assertions change only where the intentional retrieval policy
changes observable behavior. No disabled tests or weaker expected issue detection.

## Verification

From tools/bib-lint, use the existing uv-managed Python 3.12 environment:

- Focused pytest modules per task, including real SQLite consumers and HTTP fixtures.
- Full offline suite: `uv run --group dev pytest -q -m 'not package'`.
- Lint/format/complexity: `uv run --group dev invoke check`.
- Installed-package tests and both package builds.
- PDF/BibTeX paired controls; interrupted CLI resume and viewer stop/resume.
- Concurrency tests use events; pacing tests use controlled clocks.
- Review includes a deliberate mutation of early-stop or retry logic, then restores
  the implementation and checks that behavioral tests detect the mutation.

## Risks and mitigations

- Source order/evidence changes: store explicit retrieval state, preserve registry
  order in results, and version orchestration to invalidate incompatible checkpoints.
- Lost tasks after a crash: reconstruct from checkpoint, never assume durable queue
  storage implies completion or exactly-once execution.
- Shared-client evidence races: provider-owned mutable client state; synchronized
  cache access and no worker writes to reports.
- Long Retry-After: persist the full cooldown, allow other providers to advance,
  and let cancellation interrupt the wait without treating it as a citation error.
- Background callers: embed consumers without taking ownership of process signals;
  test invocation from a background thread as well as the CLI.
- Public repository hygiene: generated databases, audits, benchmarks and PDFs stay
  in ignored workspaces. Keep only implementation, regression tests and maintained docs.
