"""Shared provider ownership, cooldowns and cancellation with controlled time."""

import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.traffic import ProviderTraffic


def test_pacing_and_cooldowns_persist_between_client_instances(tmp_path):
    clock, waits = [100.0], []

    def wait(stop, seconds):
        waits.append(seconds)
        clock[0] += seconds
        return False

    traffic = ProviderTraffic(tmp_path, clock=lambda: clock[0], wait=wait)
    stop = threading.Event()
    with traffic.slot("arxiv", stop):
        traffic.wait("arxiv", 3.1, stop)
        traffic.defer("arxiv", 7)
    resumed = ProviderTraffic(tmp_path, clock=lambda: clock[0], wait=wait)
    with resumed.slot("arxiv", stop):
        resumed.wait("arxiv", 3.1, stop)
    assert clock[0] == pytest.approx(107)
    assert sum(waits) == pytest.approx(7)


def test_provider_ownership_is_shared_but_independent_providers_overlap(tmp_path):
    traffic = ProviderTraffic(tmp_path)
    stop = threading.Event()
    attempted, acquired = threading.Event(), threading.Event()

    def compete():
        attempted.set()
        with ProviderTraffic(tmp_path).slot("arxiv", stop):
            acquired.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with traffic.slot("arxiv", stop):
            future = executor.submit(compete)
            assert attempted.wait(5)
            with traffic.slot("pmlr", stop):
                assert not acquired.is_set()
        future.result(timeout=5)
    assert acquired.is_set()


def test_provider_lock_wait_is_cancellable(tmp_path):
    traffic = ProviderTraffic(tmp_path)
    stop = threading.Event()
    attempted = threading.Event()

    def compete():
        attempted.set()
        with traffic.slot("arxiv", stop):
            pytest.fail("Cancelled waiter acquired provider ownership")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with traffic.slot("arxiv", threading.Event()):
            future = executor.submit(compete)
            assert attempted.wait(5)
            stop.set()
            with pytest.raises(KeyboardInterrupt):
                future.result(timeout=5)


def test_long_cooldown_is_cancellable_without_a_real_sleep(tmp_path):
    stop = threading.Event()

    def wait(event, seconds):
        event.set()
        return True

    traffic = ProviderTraffic(tmp_path, clock=lambda: 100, wait=wait)
    with traffic.slot("arxiv", stop):
        traffic.defer("arxiv", 3600)
        with pytest.raises(KeyboardInterrupt):
            traffic.wait("arxiv", 3.1, stop)


def test_managed_http_has_one_attempt_and_sets_provider_cooldown(tmp_path):
    clock = [100.0]
    traffic = ProviderTraffic(
        tmp_path / "traffic",
        clock=lambda: clock[0],
        wait=lambda stop, seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    client.managed_retries = True
    client.traffic = traffic
    client.stop = threading.Event()
    client.method = "arxiv"
    try:
        with traffic.slot("arxiv", client.stop):
            with pytest.raises(LookupFailure) as caught:
                client.get("https://arxiv.org/abs/2401.12345")
        assert caught.value.retry_after == 60
        assert len(requests) == 1
        with traffic.slot("arxiv", client.stop):
            traffic.wait("arxiv", 3.1, client.stop)
        assert clock[0] == pytest.approx(160)
    finally:
        client.close()


def test_corrupt_local_traffic_state_is_an_execution_failure(tmp_path):
    (tmp_path / "arxiv.json").write_text("broken JSON")
    traffic = ProviderTraffic(tmp_path)
    with traffic.slot("arxiv", threading.Event()):
        with pytest.raises(OSError, match="cooldown"):
            traffic.wait("arxiv", 3.1, threading.Event())
