"""Process-wide local jobs, independent of browser sessions and HTTP handlers."""

import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from bib_lint.audit import Workspace

ACTIVE = {"running", "stopping"}


def command_for(
    source,
    workspace,
    *,
    aux=None,
    encoding=None,
    include_source=False,
    citation_key=None,
    refresh=False,
    verbose=False,
):
    command = [
        sys.executable,
        "-m",
        "bib_lint",
        "verify",
        str(Path(source).absolute()),
        "--output",
        str(workspace.root),
        "--json",
    ]
    for option, value in [("--aux", aux), ("--encoding", encoding), ("--key", citation_key)]:
        if value is not None:
            command.extend(
                [option, str(Path(value).absolute()) if option == "--aux" else str(value)]
            )
    for option, enabled in [
        ("--include-source", include_source),
        ("--refresh", refresh),
        ("--verbose", verbose),
    ]:
        if enabled:
            command.append(option)
    return command


@dataclass
class Job:
    workspace: Workspace
    command: list[str]
    owners: set[str]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = "running"
    process: object = None
    result: dict | None = None
    error: str | None = None
    logs: deque = field(default_factory=lambda: deque(maxlen=100))
    done: threading.Event = field(default_factory=threading.Event)
    guard: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self):
        with self.guard:
            return {
                "id": self.id,
                "state": self.state,
                "result": self.result,
                "error": self.error,
                "logs": list(self.logs),
            }


class Registry:
    def __init__(self, popen=None, interrupt=None):
        self.popen = popen or subprocess.Popen
        self.interrupt = interrupt or (lambda process: os.killpg(process.pid, signal.SIGINT))
        self.jobs = {}
        self.guard = threading.RLock()

    def find(self, root, owner=None):
        with self.guard:
            job = self.jobs.get(str(Path(root).resolve()))
            if job and owner:
                job.owners.add(owner)
            return job

    def start(self, source, *, output=None, owner, **options):
        workspace = Workspace.for_input(source, output)
        identity = str(workspace.root.resolve())
        with self.guard:
            if any(
                job.state in ACTIVE and (owner in job.owners or key == identity)
                for key, job in self.jobs.items()
            ):
                raise ValueError(
                    "An audit is already running; stop it and wait for exit before starting another"
                )
            job = Job(workspace, command_for(source, workspace, **options), {owner})
            self.jobs[identity] = job  # Reserve before spawning.
            try:
                job.process = self.popen(
                    job.command,
                    cwd=str(Path.cwd()),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    start_new_session=True,
                )
            except OSError as exc:
                job.state = "failed"
                job.error = f"Could not start verification: {exc}"
                job.done.set()
                return job
            threading.Thread(target=self._watch, args=(job,), daemon=True).start()
            return job

    def _watch(self, job):
        chunks = []
        overflow = [False]
        read_errors = []

        readers = [
            threading.Thread(
                target=_read_stdout, args=(job, chunks, overflow, read_errors), daemon=True
            ),
            threading.Thread(target=_read_stderr, args=(job, read_errors), daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            code = job.process.wait()
            for reader in readers:
                reader.join()
            if read_errors:
                raise ValueError("Could not read verification process output")
            result = json.loads("".join(chunks))
            status = result.get("status") if isinstance(result, dict) else None
            expected = {"completed": 0, "partial": 0, "interrupted": 130, "failed": 2}
            required = {
                "schema_version",
                "command",
                "status",
                "complete",
                "output_dir",
                "report_path",
                "checkpoint_path",
                "scope",
                "summary",
                "warnings",
                "error",
            }
            if (
                overflow[0]
                or not isinstance(result, dict)
                or not required <= result.keys()
                or result["schema_version"] != 1
                or result["command"] != "verify"
                or status not in expected
                or code != expected[status]
                or type(result["complete"]) is not bool
                or result["complete"] != (status == "completed")
                or result["scope"] not in (None, "all", "used")
                or not isinstance(result["warnings"], list)
                or any(not isinstance(w, str) for w in result["warnings"])
                or (result["summary"] is not None and not isinstance(result["summary"], dict))
                or (result["error"] is not None and not isinstance(result["error"], dict))
                or any(
                    result[k] is not None
                    and (not isinstance(result[k], str) or not Path(result[k]).is_absolute())
                    for k in ("output_dir", "report_path", "checkpoint_path")
                )
            ):
                raise ValueError("Unexpected exit or malformed final verification result")
            with job.guard:
                job.result = result
                job.state = "completed" if status in {"completed", "partial"} else status
                if status == "failed":
                    job.error = (result.get("error") or {}).get("message", "Verification failed")
        except (OSError, ValueError, TypeError) as exc:
            with job.guard:
                job.state = "failed"
                job.error = f"Verification process failed: {exc}"
        finally:
            job.done.set()

    def stop(self, job):
        with self.guard, job.guard:
            if job.state != "running":
                return
            job.state = "stopping"
            try:
                self.interrupt(job.process)
            except ProcessLookupError:
                pass  # Reader/wait thread will establish the terminal state.

    def shutdown(self):
        with self.guard:
            jobs = list(self.jobs.values())
        for job in jobs:
            if job.state in ACTIVE:
                self.stop(job)
        for job in jobs:
            if job.process is not None:
                job.process.wait()  # Reap after requesting cooperative interruption.


def _read_stdout(job, chunks, overflow, read_errors):
    size = 0
    try:
        for chunk in iter(lambda: job.process.stdout.read(4096), ""):
            size += len(chunk)
            if size <= 1_000_000:
                chunks.append(chunk)
            else:
                overflow[0] = True
    except (OSError, ValueError):
        read_errors.append("stdout")
    finally:
        job.process.stdout.close()


def _read_stderr(job, read_errors):
    # Fixed-size reads also bound a single enormous verbose response line.
    try:
        for chunk in iter(lambda: job.process.stderr.readline(1024), ""):
            with job.guard:
                job.logs.append(chunk)
    except (OSError, ValueError):
        read_errors.append("stderr")
    finally:
        job.process.stderr.close()
