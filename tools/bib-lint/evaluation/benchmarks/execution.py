"""Concurrent audit transport with the normal tool's host pacing preserved."""

import threading
import time

import httpx

from bib_lint.verification.http import MetadataClient


class HostPacer:
    def __init__(self, *, clock=time.monotonic, sleep=time.sleep):
        self.clock = clock
        self.sleep = sleep
        self.last = {}
        self.locks = {}
        self.guard = threading.Lock()

    def wait(self, host, interval):
        with self.guard:
            lock = self.locks.setdefault(host, threading.Lock())
        with lock:
            previous = self.last.get(host)
            delay = 0 if previous is None else interval - (self.clock() - previous)
            if delay > 0:
                self.sleep(delay)
            self.last[host] = self.clock()


class PacedTransport(httpx.BaseTransport):
    def __init__(self, pacer, transport=None):
        self.pacer = pacer
        self.interval = 1.0
        self.transport = transport or httpx.HTTPTransport()

    def handle_request(self, request):
        self.pacer.wait(request.url.host, self.interval)
        return self.transport.handle_request(request)

    def close(self):
        self.transport.close()


class PacedMetadataClient(MetadataClient):
    """One client per concurrent case; no shared mutable evidence or cache state."""

    def __init__(self, cache_dir, pacer):
        self.paced_transport = PacedTransport(pacer)
        super().__init__(cache_dir, transport=self.paced_transport)

    def get(self, url, **kwargs):
        policy = kwargs.get("policy")
        self.paced_transport.interval = policy.interval if policy else 1.0
        return super().get(url, **kwargs)
