import io
import json
import threading

import pytest

from bib_lint.audit import Workspace
from bib_lint.cli import final_result
from bib_lint.viewer.jobs import Registry, command_for


class Process:
    def __init__(self, result=None, code=0, logs="fetching\n"):
        self.pid = 123
        self.stdout = io.StringIO(json.dumps(result or final_result("completed")))
        self.stderr = io.StringIO(logs)
        self.release = threading.Event()
        self.code = code
        self.waits = 0

    def wait(self):
        self.waits += 1
        assert self.release.wait(3), "Test process was not released"
        return self.code


@pytest.fixture
def managed():
    processes, commands, interrupts = [], [], []

    def spawn(command, **kwargs):
        commands.append((command, kwargs))
        process = Process()
        processes.append(process)
        return process

    registry = Registry(popen=spawn, interrupt=lambda process: interrupts.append(process.pid))
    yield registry, processes, commands, interrupts
    for process in processes:
        process.release.set()
    registry.shutdown()


def test_reserved_job_duplicates_reattach_and_owner_limit(tmp_path, managed):
    registry, processes, commands, _ = managed
    job = registry.start(tmp_path / "input with spaces.bib", owner="one", output=tmp_path / "audit")
    assert job.state == "running"
    assert registry.find(job.workspace.root, "two") is job
    for owner, output in [
        ("one", tmp_path / "different"),
        ("two", tmp_path / "different"),
        ("three", tmp_path / "audit"),
    ]:
        with pytest.raises(ValueError, match="already running"):
            registry.start(tmp_path / "other.bib", owner=owner, output=output)
    assert len(processes) == 1
    command, options = commands[0]
    assert command[4] == str(tmp_path / "input with spaces.bib")
    assert options["start_new_session"] and options["stdout"] == options["stderr"]
    assert "shell" not in options
    processes[0].release.set()
    assert job.done.wait(2)
    assert job.state == "completed"
    assert registry.find(job.workspace.root) is job


def test_stop_is_once_stopping_until_exit_then_resume(tmp_path, managed):
    registry, processes, _, interrupts = managed
    job = registry.start(tmp_path / "input.bib", owner="one")
    process = processes[0]
    # The fake has no input consumed until its worker reads it. Use a separate registry
    # with an interruption envelope to cover lifecycle completion deterministically.
    process.release.set()
    assert job.done.wait(2)
    process = Process(final_result("interrupted"), code=130)
    registry.popen = lambda *_args, **_kwargs: process
    job = registry.start(tmp_path / "input.bib", owner="one")
    registry.stop(job)
    registry.stop(job)
    assert interrupts == [123] and job.state == "stopping"
    with pytest.raises(ValueError):
        registry.start(tmp_path / "input.bib", owner="one")
    process.release.set()
    assert job.done.wait(2)
    assert job.state == "interrupted"
    fresh = Process()
    fresh.release.set()
    registry.popen = lambda *_args, **_kwargs: fresh
    resumed = registry.start(tmp_path / "input.bib", owner="one")
    assert resumed.id != job.id
    assert resumed.done.wait(2)


def test_launch_failure_and_bounded_diagnostics(tmp_path):
    def fail(*_, **__):
        raise OSError("Cannot launch")

    registry = Registry(popen=fail)
    job = registry.start(tmp_path / "input.bib", owner="one")
    assert job.state == "failed" and "Cannot launch" in job.error and job.done.is_set()
    process = Process(logs="x" * 200000)
    process.release.set()
    registry.popen = lambda *_args, **_kwargs: process
    job = registry.start(tmp_path / "input.bib", owner="one")
    assert job.done.wait(2)
    assert len("".join(job.snapshot()["logs"])) <= 100 * 1024
    assert process.stdout.closed and process.stderr.closed


@pytest.mark.parametrize(
    "payload, code, state",
    [
        ("not json", 0, "failed"),
        ("{}", 0, "failed"),
        (json.dumps(final_result("completed")), 9, "failed"),
        (json.dumps(final_result("partial")), 0, "completed"),
        (
            json.dumps(
                final_result("failed", error={"code": "audit_failed", "message": "lock conflict"})
            ),
            2,
            "failed",
        ),
    ],
)
def test_process_results_and_unexpected_exit(tmp_path, payload, code, state):
    process = Process(code=code)
    process.stdout = io.StringIO(payload)
    process.release.set()
    registry = Registry(popen=lambda *_args, **_kwargs: process)
    job = registry.start(tmp_path / "input.bib", owner="one")
    assert job.done.wait(2)
    assert job.state == state
    if code == 2:
        assert job.error == "lock conflict"


def test_command_options_and_shutdown(tmp_path):
    workspace = Workspace(tmp_path / "audit")
    command = command_for(
        tmp_path / "bib.bib",
        workspace,
        aux="paper.aux",
        encoding="latin-1",
        citation_key="A",
        refresh=True,
        verbose=True,
        include_source=True,
    )
    assert "--refresh" in command and "--verbose" in command and "--include-source" in command
    assert command[command.index("--key") + 1] == "A"
    assert command[command.index("--aux") + 1].endswith("/paper.aux")
    process = Process(final_result("interrupted"), code=130)
    signals = []

    def stop(child):
        signals.append(child.pid)
        child.release.set()

    registry = Registry(popen=lambda *_args, **_kwargs: process, interrupt=stop)
    job = registry.start(tmp_path / "bib.bib", owner="one")
    registry.shutdown()
    assert job.done.wait(2)
    assert signals == [123] and process.waits >= 1


def test_real_job_invokes_cli_and_creates_zero_eligible_audit(tmp_path):
    source = tmp_path / "empty.bib"
    source.write_text("% empty bibliography")
    registry = Registry()
    job = registry.start(source, owner="real-smoke")
    try:
        assert job.done.wait(5)
        assert job.state == "completed", job.snapshot()
        assert job.result["summary"]["eligible"] == 0
        assert job.workspace.final.exists()
    finally:
        registry.shutdown()


@pytest.mark.parametrize("fault", ["oversize", "pipe", "exited"])
def test_job_output_limits_pipe_failure_and_stop_race(tmp_path, fault):
    process = Process()
    process.release.set()
    if fault == "oversize":
        process.stdout = io.StringIO("x" * 1_000_001)
    elif fault == "pipe":

        class BrokenPipe(io.StringIO):
            def readline(self, *_):
                raise OSError("pipe failed")

        process.stderr = BrokenPipe()

    def interrupt(_):
        raise ProcessLookupError

    registry = Registry(popen=lambda *_args, **_kwargs: process, interrupt=interrupt)
    if fault == "exited":
        process.release.clear()
    job = registry.start(tmp_path / "input.bib", owner="one")
    if fault == "exited":
        registry.stop(job)
        process.release.set()
    assert job.done.wait(2)
    assert job.state == ("completed" if fault == "exited" else "failed")
