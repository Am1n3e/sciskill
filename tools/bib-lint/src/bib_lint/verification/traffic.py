"""Machine-local provider ownership and persisted request cooldowns."""

import fcntl
import json
import math
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from bib_lint.storage import write_json


def pause(stop, seconds):
    return stop.wait(seconds)


class ProviderTraffic:
    def __init__(self, root=None, *, clock=None, wait=None):
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        self.root = Path(
            root or os.environ.get("BIB_LINT_PROVIDER_STATE", cache / "bib-lint/providers")
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock, self.pause = clock or time.time, wait or pause

    def _path(self, provider, suffix):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", provider):
            raise ValueError("Invalid provider traffic identity")
        return self.root / f"{provider}.{suffix}"

    @contextmanager
    def slot(self, provider, stop):
        with self._path(provider, "lock").open("a") as handle:
            while True:
                if stop.is_set():
                    raise KeyboardInterrupt
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self.pause(stop, 0.05)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _not_before(self, provider):
        try:
            value = json.loads(self._path(provider, "json").read_text())["not_before"]
        except FileNotFoundError:
            return 0
        except (ValueError, KeyError, TypeError) as exc:
            raise OSError("Invalid provider cooldown state") from exc
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise OSError("Invalid provider cooldown state")
        return value

    def wait(self, provider, interval, stop):
        # The provider slot is held throughout the lookup, including all its requests.
        deadline = self._not_before(provider)
        while deadline - self.clock() > 1e-9:
            if self.pause(stop, min(deadline - self.clock(), 0.1)):
                raise KeyboardInterrupt
        if stop.is_set():
            raise KeyboardInterrupt
        write_json(self._path(provider, "json"), {"not_before": self.clock() + interval})

    def defer(self, provider, seconds):
        deadline = max(self._not_before(provider), self.clock() + seconds)
        write_json(self._path(provider, "json"), {"not_before": deadline})
