"""Provider-owned SQLite queues; Huey owns worker loops and scheduled retries."""

import logging
import secrets
import sys
import threading
from contextlib import ExitStack
from queue import Empty, SimpleQueue

from huey import SqliteHuey
from huey.consumer import Consumer
from huey.serializer import SignedSerializer

from bib_lint.storage import report_lock
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.registry import validate_registry

RETRY_DELAY = 2
MAX_SCHEDULE_DELAY = 86400


class RetryLookup(Exception):
    def __init__(self, result, delay=0):
        self.result, self.delay = result, delay
        super().__init__(result.get("error", {}).get("code", "Temporary provider failure"))


class FailureLogger(logging.LoggerAdapter):
    def __init__(self, logger, failures, stop):
        super().__init__(logger, {})
        self.failures, self.stop = failures, stop

    def log(self, level, message, *args, **kwargs):
        if level >= logging.ERROR:
            self.failures.put(sys.exc_info()[1] or RuntimeError(message % args))
            self.stop.set()
        super().log(level, message, *args, **kwargs)


class EmbeddedConsumer(Consumer):
    def __init__(self, *args, failures, stop, **kwargs):
        self.failures, self.audit_stop = failures, stop
        super().__init__(*args, **kwargs)
        self._logger = FailureLogger(self._logger, failures, stop)

    def _create_process(self, process, name):
        process._logger = FailureLogger(process._logger, self.failures, self.audit_stop)
        return super()._create_process(process, name)

    def _set_signal_handlers(self):
        # The audit owns cancellation, including when called from a background thread.
        # Huey 3.5.3 exposes no constructor option to disable its signal installation.
        pass

    def check_alive(self):
        threads = [thread for _, thread in self.worker_threads] + [self.scheduler]
        if any(not thread.is_alive() for thread in threads):
            raise LookupError("Provider worker exited; resume the checkpoint to recover its task")


def _register(queue, lookup, provider, stop, retries, retry_delay):
    @queue.task(
        context=True, retries=retries, retry_delay=retry_delay, retry_backoff=2, name="lookup"
    )
    def execute(entry, phase, state, task=None):
        if stop.is_set():
            return {"interrupted": True}
        try:
            return lookup(entry, provider, phase, state)
        except RetryLookup as exc:
            if task.retries and 0 <= exc.delay <= MAX_SCHEDULE_DELAY:
                task.retry_delay = max(task.retry_delay, exc.delay)
                raise
            return exc.result
        except KeyboardInterrupt:
            stop.set()
            return {"interrupted": True}
        except BaseException as exc:
            return {"fatal": f"{type(exc).__name__}: {exc}", "fatal_type": type(exc).__name__}

    return execute


class ProviderQueues:
    def __init__(self, root, lookup, *, providers=METHODS, stop=None, retries=2, retry_delay=None):
        root.mkdir(parents=True, exist_ok=True)
        self.root, self.lookup = root, lookup
        self.providers = validate_registry(providers)
        self.stop = stop if stop is not None else threading.Event()
        self.tasks, self.queues, self.consumers = {}, {}, []
        self.failures = SimpleQueue()
        self.submitted = 0
        self.stack = ExitStack()
        self.serializer = SignedSerializer(secret=secrets.token_hex(32))
        for name in self.providers:
            queue = SqliteHuey(
                name,
                filename=str(root / f"{name}.db"),
                serializer=self.serializer,
                store_intermediate_errors=False,
                strict_fifo=True,
                fsync=True,
                cache_mb=1,
            )
            self.queues[name] = queue
            self.tasks[name] = _register(
                queue,
                lookup,
                name,
                self.stop,
                retries,
                RETRY_DELAY if retry_delay is None else retry_delay,
            )

    def submit(self, entry, provider, phase):
        result = self.tasks[provider](entry, phase, {})
        self.submitted += 1
        return result

    def __enter__(self):
        self.stack.enter_context(report_lock(self.root / "owner"))
        try:
            for queue in self.queues.values():
                # The report checkpoint, rather than potentially orphaned queue work,
                # determines what to replay. Clear before deserializing any old payload.
                queue.flush()
                self.stack.callback(queue.storage.close)
                consumer = EmbeddedConsumer(
                    queue,
                    failures=self.failures,
                    stop=self.stop,
                    workers=1,
                    worker_type="thread",
                    periodic=False,
                    initial_delay=0.01,
                    max_delay=0.05,
                    check_worker_health=False,
                )
                self.consumers.append(consumer)
                consumer.start()
        except BaseException:
            self.close()
            raise
        return self

    def check(self):
        self._raise_failure()
        for consumer in self.consumers:
            consumer.check_alive()

    def _raise_failure(self):
        try:
            failure = self.failures.get_nowait()
        except Empty:
            return
        if isinstance(failure, (OSError, ValueError)):
            raise failure
        raise LookupError(f"Provider queue failed: {failure}") from failure

    def close(self):
        self.stop.set()
        # Stop every dequeue loop before joining any provider's active lookup.
        for consumer in self.consumers:
            consumer.stop()
        for consumer in self.consumers:
            consumer.stop(graceful=True)
        self.stack.close()

    def __exit__(self, exc_type, *_):
        self.close()
        self._raise_failure()
