# Locator-first provider queues: implementation checklist

## T01: Managed runtime
- [x] Promote Huey into both runtime dependency sets and lock it.
- [x] Embed one SQLite consumer/worker per provider without installing signal handlers.
- [x] Stop all consumers before joining; preserve worker fatal errors and cancellation.
Verification: queue serialization/overlap, background invocation, shutdown and build tests.
Files: verification/queues.py, dependency metadata/lock, tests/test_queues.py.
Dependencies: none.

## T02: Locator-first retrieval
- [x] Plan supplied URLs and valid provider identifiers before title/catalog discovery.
- [x] Compare direct records with untouched citation fields through existing helpers.
- [x] Preserve mismatches, missing fields, secondary locators and publication ambiguity.
Verification: routing, direct success/mismatch, identifier conflicts and fallback tests.
Files: verification/routing.py, verification/__init__.py, tests/test_routing.py.
Dependencies: T01.

## T03: Provider traffic and retries
- [x] Serialize provider execution across independent audits and pace actual requests.
- [x] Honor shared Retry-After cooldowns; cancel lock and pacing waits promptly.
- [x] Schedule bounded transient retries through Huey with a shared HTTP-attempt budget.
- [x] Serialize shared cache operations without changing report-lock failure behavior.
Verification: controlled clocks, concurrent audits, retry exhaustion, cancellation and cache tests.
Files: verification/traffic.py, verification/http.py, providers/context.py, verification/cache.py,
       tests/test_traffic.py (split retry tests into tests/test_queues.py).
Dependencies: T01.

## Checkpoint C1
- [x] Routing and runtime contracts pass; each provider owns its mutable request state.

## T04: Checkpoint coordinator
- [x] Integrate queues into the one shared report verifier for PDF and BibTeX.
- [x] Save each completed lookup, resume remaining phases, and invalidate old decisions.
- [x] Reconcile orphaned SQLite tasks from checkpoint state; refresh only selected entries.
Verification: existing resume/workspace tests plus interruption between lookup phases and recovery.
Files: verification/__init__.py, verification/workflow.py, tests/test_resume.py,
       tests/test_provider_workflow.py, tests/test_queued_audit.py.
Dependencies: T02, T03.

## T05: Resolver handoff
- [ ] Resolve DOI redirects without following unknown hosts; hand paper URLs to provider queues.
- [ ] Normalize supported provider PDF links to authoritative metadata records.
- [ ] Preserve all original identifiers and locator diagnostics.
Verification: redirects, unsafe destinations, chains, PDF-link and conflicting DOI tests.
Files: verification/routing.py, verification/resolver.py, tests/test_routing.py,
       tests/test_queued_audit.py.
Dependencies: T04.

## Checkpoint C2
- [ ] BibTeX and PDF audit through the production CLI, with correct evidence and resume.

## T06: Product acceptance
- [ ] Verify CLI/viewer stop/resume, progress and machine envelopes.
- [ ] Verify source errors remain findings while local execution failures stop the audit.
- [ ] Verify installed distributions include Huey and work without development modules.
Verification: full offline regressions, package tests and shared launcher checks.
Files: CLI/viewer regression tests, package tests and acceptance harness as required.
Dependencies: T05.

## T07: Review and simplify
- [ ] Review correctness, lifecycle, concurrency, safety and dependencies.
- [ ] Remove prototype duplication and unnecessary scheduler/verdict abstractions.
- [ ] Document actual retrieval policy, rate scope, recovery and limits.
- [ ] Run mutation check, full regression suite, quality checks and package builds.
Verification: review findings addressed; tests retain their original strength.
Files: evaluation prototype files, README/skill docs, affected implementation and tests.
Dependencies: T06.

## Complete
- [ ] All tasks and verification evidence recorded; working tree ready for review.
