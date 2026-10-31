# URL-first verification prototype

This experiment evaluates Huey with SQLite and a different retrieval policy. It
does not change `bib-lint verify`, the viewer, or production consensus. Huey is a
development dependency. The code accepts the normalized entry dictionaries shared
by PDF and BibTeX inputs; it does not replace PDF extraction or its evidence checks.

## Retrieval policy

1. Route a supplied paper URL to its provider using the existing locator validators
   and the provider's exact host allowlist. Unknown sites and DOI resolver URLs are
   not fetched directly. A provider homepage is not a paper locator.
2. Enqueue one direct lookup for a recognized URL. Retrieve using the URL alone,
   without title discovery or another supplied identifier overriding it. An arXiv
   URL becomes an ID lookup through the existing arXiv API adapter.
3. A single record with a title, authors, and year resolves the URL. Compare it
   against the original citation, retaining identifier conflicts and unverified
   secondary locators. A wrong paper or year is a mismatch, not a reason to silently
   find a different paper. Missing input metadata requires review.
4. Stop discovery for that citation once the URL resolves, including when the
   comparison reports a mismatch or needs review. An HTTP 200 with no usable paper
   metadata is unresolved.
5. For an unresolved URL, enqueue title discovery at that provider, followed by
   other providers in registry order, one at a time. Without a routable URL, begin
   with registry order. Stop at a resolved result. History retains each outcome.

For 100 citations with resolving URLs this creates 100 tasks. Missing URLs or
failed resolution create additional tasks only as needed. Worst-case exhaustive
discovery still visits every provider; failed direct lookups add work in that case.
Venue-based ordering and resolving identifier-only citations before searching are
not implemented in this prototype.

## Huey and SQLite

`ProviderQueues` registers one lookup task and starts one threaded Huey consumer
per provider, with one worker each. Each consumer also starts a scheduler: six
providers use twelve background threads in one Python process. SQLite queues use
separate database files, WAL, durable writes, strict FIFO, and a 1 MB page-cache
setting per connection. There is no Redis server or separately launched daemon.

The parent coordinates results and lazy fallback; Huey implements the worker
loops, serialization, scheduled retries, and result storage. Embedded startup
restores the parent's signal handlers and context exit joins the consumers.
An ownership lock prevents two consumers using the same experiment directory.

Transient network errors, HTTP 429, and HTTP 5xx responses use bounded Huey retries
with exponential backoff. Missing records and other provider failures return
unresolved outcomes. Local storage failures and unexpected exceptions stop the
coordinator without retrying. Intermediate retry errors are withheld so the
coordinator cannot start fallback while a retry is still scheduled.

`lookup_entry(entry, provider, phase, client)` uses real adapters and shared field
comparison/input checks. Supply a separate long-lived `MetadataClient` for each
provider and isolated cache directories. The test suite exercises real adapters
with mocked HTTP alongside actual SQLite consumers.

## Reproduce the offline measurements

From `tools/bib-lint`, using a fresh output directory each time:

```sh
uv sync --locked --group dev
uv run --locked --group dev python -m evaluation.url_first_benchmark \
  --root evaluation/.artifacts/url-first-noop --citations 100
uv run --locked --group dev python -m evaluation.url_first_benchmark \
  --root evaluation/.artifacts/url-first-latency --citations 100 --latency 0.05
uv run --locked --group dev pytest -q tests/test_url_first.py
```

The benchmark uses synthetic successful lookups distributed across all six
providers. It makes no network requests. Wall time includes queue/database setup,
consumer startup, submission, result collection, and graceful shutdown. Database
bytes include remaining SQLite/WAL files. Timings are samples, not thresholds.

Example local measurements for 100 citations:

| Simulated lookup work | URL-first tasks / wall time | All-source tasks / wall time |
| --- | --- | --- |
| None | 100 / 0.174 s | 600 / 0.647 s |
| 50 ms per task | 100 / 1.142 s | 600 / 6.113 s |

The no-op runs used approximately 240 KiB and 384 KiB of database storage,
respectively. They do not measure process memory or actual provider latency.
Generated queues and results belong under the ignored `evaluation/.artifacts/`.

## Boundaries before production integration

- A single-source verdict is not multi-source consensus. In particular, an arXiv
  resolution does not establish whether a later published version exists.
  Preprint/publication differences and incomplete evidence require review.
- The prototype has no complete audit CLI, report checkpoint integration, or crash
  reconciliation. SQLite retains pending tasks, but an abruptly interrupted
  in-flight Huey task can be lost. Recovery must reconcile missing task results
  against persisted reference/provider state; queue persistence alone is not enough.
- One worker per provider is enforced within an experiment directory. Different
  audit directories/processes are not globally coordinated.
- Request pacing stays in the supplied HTTP client. Production integration needs a
  provider-wide cooldown shared across citations, including when a retry is delayed
  after HTTP 429. Huey's task retry delay alone does not provide this.
- Existing HTTP retries and whole-lookup retries can multiply attempts. Establish
  an overall request budget before enabling live scheduled retries.
- PDF uncertainty must still gate the final report. A matching source record does
  not establish that extraction identified every reference or reconstructed it
  correctly. Preserve the existing extraction checks at report integration.
- Adapter support for direct PDF links varies; recognized links without usable
  metadata fall back to discovery. DOI redirects and broader URL normalization
  require separate retrieval and host-validation work.
- Embedded consumers do not run Huey's supervisor loop in this experiment. Worker
  health supervision and bounded cancellation need integration with the audit's
  lifecycle before this becomes the default implementation.

Reference behavior: [Huey SQLite and consumer APIs](https://huey.readthedocs.io/en/stable/api.html),
[retry and interrupted-task semantics](https://huey.readthedocs.io/en/stable/guide.html).
