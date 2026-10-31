"""Production queue lifecycle and retry contracts with real SQLite consumers."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

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


def test_huey_result_storage_failure_reaches_coordinator(tmp_path, monkeypatch):
    with ProviderQueues(
        tmp_path, lambda *args: {"ok": True}, providers={"pmlr": METHODS["pmlr"]}
    ) as queues:

        def fail(*args, **kwargs):
            raise OSError("result storage is full")

        monkeypatch.setattr(queues.queues["pmlr"], "put_result", fail)
        queues.submit({}, "pmlr", "search")
        failure = queues.failures.get(timeout=5)
        queues.failures.put(failure)
        with pytest.raises(OSError, match="storage is full"):
            queues.check()


def test_unrepresentable_retry_delay_does_not_orphan_a_task(tmp_path):
    with ProviderQueues(
        tmp_path,
        lambda *args: (_ for _ in ()).throw(RetryLookup({"status": "error"}, delay=1e100)),
        providers={"pmlr": METHODS["pmlr"]},
    ) as queues:
        assert queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5) == {
            "status": "error"
        }


def test_infrastructure_failure_is_not_hidden_by_cancellation(tmp_path):
    try:
        with ProviderQueues(
            tmp_path, lambda *args: {}, providers={"pmlr": METHODS["pmlr"]}
        ) as queues:
            queues.failures.put(OSError("queue storage failed"))
            raise KeyboardInterrupt
    except OSError as exc:
        assert "queue storage failed" in str(exc)
    except KeyboardInterrupt:
        pytest.fail("Cancellation hid the actual infrastructure failure")


@pytest.mark.parametrize("started_threads", [0, 1, 2, 3])
def test_partial_startup_preserves_error_releases_owner_and_joins_threads(
    tmp_path, monkeypatch, started_threads
):
    before = set(threading.enumerate())
    original_start = threading.Thread.start
    attempts = []

    def start(thread):
        if len(attempts) == started_threads:
            raise RuntimeError("unable to start new thread")
        attempts.append(thread)
        return original_start(thread)

    providers = {name: METHODS[name] for name in ("pmlr", "arxiv")}
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", start)
        with pytest.raises(RuntimeError, match="unable to start new thread"):
            with ProviderQueues(tmp_path, lambda *args: {}, providers=providers):
                pytest.fail("Startup must fail")
    assert set(threading.enumerate()) == before
    with ProviderQueues(tmp_path, lambda *args: {"ok": True}, providers=providers) as queues:
        assert queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5) == {"ok": True}
