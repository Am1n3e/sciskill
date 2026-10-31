"""Production queue lifecycle and retry contracts with real SQLite consumers."""

import threading
from concurrent.futures import ThreadPoolExecutor

from bib_lint.verification.providers import METHODS
from bib_lint.verification.queues import ProviderQueues, RetryLookup


def test_queues_embed_in_a_background_caller(tmp_path):
    def run():
        with ProviderQueues(
            tmp_path, lambda entry, name, phase, state: entry, providers={"pmlr": METHODS["pmlr"]}
        ) as queues:
            return queues.submit({"key": "one"}, "pmlr", "search").get(blocking=True, timeout=5)

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(run).result(timeout=10) == {"key": "one"}


def test_retry_state_survives_huey_scheduling(tmp_path):
    attempts = []

    def lookup(entry, name, phase, state):
        state["attempts"] = state.get("attempts", 0) + 1
        attempts.append(state["attempts"])
        if state["attempts"] == 1:
            raise RetryLookup({"status": "error"})
        return {"status": "found", "attempts": state["attempts"]}

    with ProviderQueues(
        tmp_path, lookup, providers={"pmlr": METHODS["pmlr"]}, retry_delay=1
    ) as queues:
        result = queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5)
    assert result == {"status": "found", "attempts": 2}
    assert attempts == [1, 2]


def test_retry_exhaustion_returns_the_provider_finding(tmp_path):
    attempts = []

    def lookup(*args):
        attempts.append(1)
        raise RetryLookup({"status": "error", "error": {"code": "network_error"}})

    with ProviderQueues(
        tmp_path, lookup, providers={"pmlr": METHODS["pmlr"]}, retries=1, retry_delay=1
    ) as queues:
        result = queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5)
    assert result["error"]["code"] == "network_error"
    assert len(attempts) == 2


def test_shutdown_cancels_active_waits_before_joining(tmp_path):
    stop = threading.Event()
    started = threading.Event()

    def lookup(*args):
        started.set()
        assert stop.wait(5), "Cancellation was not delivered before joining workers"
        raise KeyboardInterrupt

    before = set(threading.enumerate())
    with ProviderQueues(tmp_path, lookup, providers={"pmlr": METHODS["pmlr"]}, stop=stop) as queues:
        queues.submit({}, "pmlr", "search")
        assert started.wait(5)
    assert set(threading.enumerate()) == before


def test_local_failure_is_not_scheduled_for_retry(tmp_path):
    calls = []

    def lookup(*args):
        calls.append(1)
        raise OSError("disk full")

    with ProviderQueues(tmp_path, lookup, providers={"pmlr": METHODS["pmlr"]}) as queues:
        result = queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5)
    assert "disk full" in result["fatal"]
    assert len(calls) == 1


def test_abandoned_queue_work_is_rebuilt_from_checkpoint_not_replayed(tmp_path):
    calls = []
    abandoned = ProviderQueues(
        tmp_path, lambda *args: calls.append("old"), providers={"pmlr": METHODS["pmlr"]}
    )
    abandoned.submit({}, "pmlr", "search")
    abandoned.queues["pmlr"].storage.close()
    with ProviderQueues(
        tmp_path, lambda *args: {"fresh": True}, providers={"pmlr": METHODS["pmlr"]}
    ) as queues:
        result = queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5)
    assert result == {"fresh": True}
    assert calls == []
