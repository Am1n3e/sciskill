"""Coordinate locator phases and provider queues; only the caller writes reports."""

import copy
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from queue import Empty, SimpleQueue

from bib_lint.storage import ReportLockError
from bib_lint.verification.http import LookupFailure
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import LookupQuery
from bib_lint.verification.queues import ProviderQueues, RetryLookup
from bib_lint.verification.routing import LookupStep, plan_lookups, resolved
from bib_lint.verification.traffic import ProviderTraffic


def _consume_attempt(state, maximum):
    used = state.get("attempts", 0)
    if used >= maximum:
        raise LookupFailure("incomplete_search", "HTTP attempt budget exhausted across retries")
    state["attempts"] = used + 1


def _retryable(result):
    error = result.get("error", {})
    return error.get("code") in {"network_error", "rate_limited"} or (
        error.get("code") == "http_error" and error.get("message", "").startswith("HTTP 5")
    )


class ProviderLookup:
    def __init__(self, client, providers, stop, events):
        self.providers, self.stop, self.events = providers, stop, events
        self.traffic = ProviderTraffic()
        self.clients = {}
        # HTTPX's pool is thread-safe; mutable evidence and request scope are not shared.
        for name in providers:
            scoped = copy.copy(client)
            scoped.evidence, scoped.last_request = [], {}
            scoped.managed_retries = True
            scoped.traffic, scoped.stop = self.traffic, stop
            self.clients[name] = scoped

    def __call__(self, entry, name, phase, state):
        from bib_lint.verification import _execute_provider

        provider, client = self.providers[name], self.clients[name]
        step, query = LookupStep(**phase), LookupQuery.from_entry(entry)
        with self.traffic.slot(name, self.stop):
            client.evidence = []
            client.progress = lambda message: self.events.put(f"  {name}: {message}")
            client.attempt_budget = lambda: _consume_attempt(
                state, provider.descriptor.request_policy.max_attempts
            )
            context = RequestContext(client, provider.descriptor, query.citation_key)
            result = _execute_provider(
                name, provider, query, context, retrieval=step.query(query), strategy=step.strategy
            )
            state.setdefault("requests", []).extend(client.evidence)
            result.update(
                adapter_version=provider.descriptor.adapter_version,
                display_name=provider.descriptor.display_name,
                evidence_category=provider.descriptor.evidence_category,
                canonical_priority=provider.descriptor.canonical_priority,
                requests=state["requests"],
                checked_at=datetime.now(UTC).isoformat(),
            )
            if _retryable(result):
                raise RetryLookup(result, result.get("error", {}).get("retry_after", 0))
            return result


@dataclass
class ReferenceRun:
    item: dict
    steps: list
    index: int = 0
    future: object = None

    def submit(self, queues, progress):
        step = self.steps[self.index]
        if progress:
            progress(f"  {step.provider}: Fetching ...")
        self.future = queues.submit(self.item["entry"], step.provider, asdict(step))


def _result(future):
    result = future.get()
    if result.get("fatal"):
        errors = {"ReportLockError": ReportLockError, "OSError": OSError, "ValueError": ValueError}
        raise errors.get(result.get("fatal_type"), RuntimeError)(result["fatal"])
    if result.get("interrupted"):
        raise KeyboardInterrupt
    return result


def _ready(reference, save, progress):
    from bib_lint.verification import _source_progress

    result = _result(reference.future)
    step = reference.steps[reference.index]
    stop_search = step.strategy != "search" and resolved(result)
    next_index = reference.index + 1
    complete = stop_search or next_index == len(reference.steps)
    save(reference.item, result, step, next_index, complete, stop_search)
    reference.index, reference.future = next_index, None
    if progress:
        _source_progress(step.provider, result, progress)
        if complete:
            from bib_lint.status import reference_status

            correctness = reference.item["validations"]["correctness"]
            progress(f"  status: {reference_status(reference.item['validations']).lower()}")
            consensus = correctness["consensus"]
            progress(f"  found: {consensus['records_found']}/{consensus['applicable']}")
            progress(f"  consensus: {consensus['display']}")
    return complete


def _progress(events, progress):
    while True:
        try:
            message = events.get_nowait()
        except Empty:
            return
        if progress:
            progress(message)


def _references(items, providers, progress):
    from bib_lint.status import source_status

    references = []
    for number, item in enumerate(items, 1):
        previous = item["validations"].get("correctness", {})
        if progress:
            progress(f"Verifying {number}/{len(items)}: {item['entry'].get('key', '?')}")
            for method in previous.get("methods", []):
                progress(f"  {method['name']}: Resumed ({source_status(method['status'])})")
        if previous.get("complete"):
            continue
        references.append(
            ReferenceRun(
                item,
                plan_lookups(item["entry"], providers),
                previous.get("retrieval", {}).get("next", 0),
            )
        )
    return references


def _drain(pending, save, progress):
    for reference in pending:
        if reference.future and reference.future.is_ready():
            result = reference.future.get()
            if not result.get("fatal") and not result.get("interrupted"):
                _ready(reference, save, progress)


def audit_entries(items, providers, client, queue_root, save, progress=None):
    pending = _references(items, providers, progress)
    if not pending:
        return
    events, stop = SimpleQueue(), threading.Event()
    lookup = ProviderLookup(client, providers, stop, events)
    try:
        with ProviderQueues(queue_root, lookup, providers=providers, stop=stop) as queues:
            for reference in pending:
                reference.submit(queues, progress)
            while pending:
                queues.check()
                _progress(events, progress)
                for reference in pending.copy():
                    if not reference.future.is_ready():
                        continue
                    if _ready(reference, save, progress):
                        pending.remove(reference)
                    else:
                        reference.submit(queues, progress)
                stop.wait(0.01)
    finally:
        # Consumers have joined. Preserve finished work even when another task failed
        # or the main thread was interrupted before it consumed a completed result.
        _progress(events, progress)
        _drain(pending, save, progress)
