"""Embedded Huey consumers for a single, isolated prototype run."""

import signal
from contextlib import ExitStack

from huey import SqliteHuey

from bib_lint.storage import report_lock
from bib_lint.verification.http import LookupFailure
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.registry import validate_registry


def _retryable(exc):
    return exc.code in {"network_error", "rate_limited"} or (
        exc.code == "http_error" and str(exc).startswith("HTTP 5")
    )


def _register(queue, lookup, provider, retries, retry_delay):
    @queue.task(retries=retries, retry_delay=retry_delay, retry_backoff=2, name="lookup")
    def execute(entry, phase):
        try:
            result = lookup(entry, provider, phase)
            if not isinstance(result, dict) or result.get("outcome") not in {
                "resolved",
                "unresolved",
            }:
                raise ValueError("Lookup must return a resolved or unresolved outcome")
            return result
        except LookupFailure as exc:
            if _retryable(exc):
                raise
            return {"outcome": "unresolved", "error": {"code": exc.code, "message": str(exc)}}
        except Exception as exc:
            return {"outcome": "fatal", "error": f"{type(exc).__name__}: {exc}"}

    return execute


class ProviderQueues:
    """One SQLite file and one managed worker per provider; no custom worker loop.

    Call from the main thread. Consumers temporarily install process signal handlers.
    Use an isolated directory: these queues are not a shared background service.
    """

    def __init__(self, root, lookup, *, providers=METHODS, retries=2, retry_delay=1):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.providers = validate_registry(providers)
        self.tasks, self.queues = {}, {}
        self.consumers = []
        self.submitted = 0
        for name in self.providers:
            queue = SqliteHuey(
                name,
                filename=str(root / f"{name}.db"),
                store_intermediate_errors=False,
                strict_fifo=True,
                fsync=True,
                cache_mb=1,
            )
            self.queues[name] = queue
            self.tasks[name] = _register(queue, lookup, name, retries, retry_delay)

    def submit(self, entry, provider, phase):
        result = self.tasks[provider](entry, phase)
        self.submitted += 1
        return result

    def __enter__(self):
        self.stack = ExitStack()
        self.stack.enter_context(report_lock(self.root / "owner"))
        self.handlers = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        }
        self.stack.callback(self._restore_handlers)
        try:
            for queue in self.queues.values():
                self.stack.callback(queue.storage.close)
                consumer = queue.create_consumer(
                    workers=1,
                    worker_type="thread",
                    periodic=False,
                    initial_delay=0.01,
                    max_delay=0.05,
                    check_worker_health=False,
                )
                self.consumers.append(consumer)
                self.stack.callback(consumer.stop, graceful=True)
                consumer.start()
                self._restore_handlers()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _restore_handlers(self):
        for sig, handler in self.handlers.items():
            signal.signal(sig, handler)

    def __exit__(self, *_):
        self.stack.close()
