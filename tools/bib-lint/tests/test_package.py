"""Isolated tool installs: dependencies may be fetched; providers are never queried."""

import json
import os
import signal
import socket
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def wait_for_viewer(server, base_url, log_path, *, timeout=30):
    deadline = time.monotonic() + timeout
    last = "No response received"
    # urllib discovers macOS system proxies as well as environment proxies.
    # Readiness must take the same explicit direct-loopback route as the browser.
    with httpx.Client(base_url=base_url, trust_env=False, timeout=1) as browser:
        while time.monotonic() < deadline:
            code = server.poll()
            if code is not None:
                last = f"Viewer process exited {code}"
                break
            try:
                response = browser.get("/api/state")
                last = f"HTTP {response.status_code}: {response.text[:2000]}"
                state = response.json()
                if (
                    response.status_code == 200
                    and isinstance(state, dict)
                    and "summary" in state
                    and state["summary"] is None
                ):
                    return state
            except (httpx.HTTPError, ValueError) as exc:
                last = repr(exc)
            time.sleep(0.1)
    output = log_path.read_text()[-4000:] if log_path.exists() else "No server log"
    raise AssertionError(f"Installed viewer did not become ready: {last}\nServer output:\n{output}")


def test_installed_wheel_and_local_install_modes(tmp_path):
    env = dict(
        os.environ,
        UV_TOOL_DIR=str(tmp_path / "tools"),
        UV_TOOL_BIN_DIR=str(tmp_path / "bin"),
        UV_NO_PROGRESS="1",
    )
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    artifacts = tmp_path / "artifacts"
    run(["uv", "build", "--out-dir", str(artifacts)], ROOT, env)
    wheel = next(artifacts.glob("*.whl"))
    required = {
        "bib_lint/cli.py",
        "bib_lint/audit.py",
        "bib_lint/scope.py",
        "bib_lint/citation_keys.py",
        "bib_lint/pdf_evidence.py",
        "bib_lint/pdf_input/__init__.py",
        "bib_lint/pdf_input/worker.py",
        "bib_lint/pdf_input/layout.py",
        "bib_lint/pdf_input/citations.py",
        "bib_lint/verification/input_checks.py",
        "bib_lint/verification/queues.py",
        "bib_lint/verification/workflow.py",
        "bib_lint/verification/traffic.py",
        "bib_lint/verification/routing.py",
        "bib_lint/verification/resolver.py",
        "bib_lint/viewer/app.py",
        "bib_lint/viewer/server.py",
        "bib_lint/viewer/presentation.py",
        "bib_lint/viewer/static/index.html",
        "bib_lint/viewer/static/app.js",
        "bib_lint/viewer/static/styles.css",
        "bib_lint/viewer/jobs.py",
        "bib_lint/verification/providers/protocol.py",
        "bib_lint/verification/providers/registry.py",
        "bib_lint/verification/providers/context.py",
        "bib_lint/verification/providers/arxiv.py",
        "bib_lint/verification/providers/pmlr.py",
        "bib_lint/verification/providers/jmlr.py",
        "bib_lint/verification/providers/acl_anthology.py",
        "bib_lint/verification/providers/neurips.py",
        "bib_lint/verification/providers/openreview.py",
    }
    with zipfile.ZipFile(wheel) as archive:
        assert required <= set(archive.namelist())
        metadata = archive.read(
            next(n for n in archive.namelist() if n.endswith("/METADATA"))
        ).decode()
        assert "Requires-Python: >=3.12" in metadata
        assert "Requires-Dist: streamlit" not in metadata
        assert "Requires-Dist: pdfplumber" in metadata
        assert "Requires-Dist: cryptography" in metadata
        assert "Requires-Dist: huey" in metadata
        dependencies = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
        assert not any("pytest" in line or "coverage" in line for line in dependencies)
    with tarfile.open(next(artifacts.glob("*.tar.gz"))) as archive:
        assert all(
            any(n.endswith("/src/" + module) for n in archive.getnames()) for module in required
        )
    paper = tmp_path / "paper"
    paper.mkdir()
    bib = paper / "empty.bib"
    bib.write_text("% no eligible references")
    run(["uv", "tool", "install", str(wheel)], paper, env)
    executable = tmp_path / "bin/bib-lint"
    python = tmp_path / "tools/bib-lint/bin/python"
    location = run(
        [str(python), "-c", "import bib_lint; print(bib_lint.__file__)"], paper, env
    ).stdout
    assert str(ROOT) not in location
    script = """from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.registry import validate_registry
expected = ['arxiv','pmlr','jmlr','acl_anthology','neurips','openreview']
assert list(validate_registry(METHODS)) == expected
assert all(p.descriptor.adapter_version for p in METHODS.values())
"""
    run([str(python), "-c", script], paper, env)
    assert "bib-lint 0.1.0" in run([str(executable), "--version"], paper, env).stdout
    assert "{verify,view}" in run([str(executable), "--help"], paper, env).stdout
    result = json.loads(run([str(executable), "verify", "empty.bib", "--json"], paper, env).stdout)
    assert result["complete"] and result["summary"]["eligible"] == 0
    assert Path(result["output_dir"]) == paper / "empty.bib-lint"
    assert Path(result["report_path"]).is_file() and result["checkpoint_path"] is None
    assert not (paper / "empty.bib-lint/cache/checksum.json").exists()
    assert bib.read_text() == "% no eligible references"
    # Exercise installed backend resources without importing from the checkout.
    script = """from importlib.resources import files
from bib_lint.viewer.app import ViewerSession
from bib_lint.viewer.jobs import Registry
assert ViewerSession(Registry()).state()['summary'] is None
assert 'Audit setup' in files('bib_lint.viewer').joinpath('static/index.html').read_text()
"""
    run([str(python), "-c", script], paper, env)
    check_installed_pdf(python, executable, paper, env)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log_path = tmp_path / "installed-viewer.log"
    with log_path.open("w") as server_log:
        server = subprocess.Popen(
            [str(executable), "view", "--port", str(port), "--no-browser"],
            cwd=paper,
            env=env,
            stdout=server_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    try:
        wait_for_viewer(server, f"http://127.0.0.1:{port}", log_path)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as browser:
            assert browser.get("/").status_code == 200
            assert "Science Skills" in browser.get("/").text
            assert browser.get("/app.js").status_code == 200
            state = browser.get("/api/state").json()
            started = browser.post(
                "/api/action",
                json={"action": "verify", "bibliography": str(bib)},
                headers={"X-CSRF-Token": state["csrf"]},
            )
            assert started.status_code == 200
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = browser.get("/api/state").json()
                if state["job"]["state"] not in {"running", "stopping"}:
                    break
                time.sleep(0.05)
            assert state["job"]["state"] == "completed", state
            assert state["job"]["result"]["complete"] is True
            assert state["summary"]["total"] == 0
    finally:
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGINT)
        server.communicate(timeout=10)
    # Verify the README's normal and editable checkout installs in the same disposable tool store.
    for mode in [[], ["--editable"]]:
        run(["uv", "tool", "install", *mode, str(ROOT), "--force"], paper, env)
        assert "bib-lint 0.1.0" in run([str(executable), "--version"], paper, env).stdout
        result = json.loads(
            run(
                [str(executable), "verify", "empty.bib", "--json", "-o", "other-audit"], paper, env
            ).stdout
        )
        assert (
            result["status"] == "completed" and Path(result["output_dir"]) == paper / "other-audit"
        )


def check_installed_pdf(python, executable, paper, env):
    from reportlab.pdfgen import canvas

    source = paper / "references paper.PDF"
    output = canvas.Canvas(str(source), invariant=1)
    output.setFont("Times-Bold", 12)
    output.drawString(50, 700, "References")
    output.setFont("Times-Roman", 10)
    output.drawString(50, 680, "[1] Jane Smith. An Example Paper. Example Journal, 2025.")
    output.save()
    before = source.read_bytes()
    script = """import socket
from pathlib import Path
from bib_lint.viewer.app import ViewerSession
from bib_lint.viewer.jobs import Registry
from bib_lint.pdf_input import extract_pdf
from bib_lint.scope import validate_report

def forbidden(*args, **kwargs):
    raise AssertionError('PDF preview attempted a network request')
socket.socket.connect = forbidden
source = Path('references paper.PDF')
report = extract_pdf(source)
validate_report(report)
assert report['schema_version'] == 4 and len(report['items']) == 1
assert report['items'][0]['entry']['fields']['title'] == 'An Example Paper'
session = ViewerSession(Registry())
state = session.action({'action':'parse','bibliography':str(source),'output':'pdf-audit'})
assert state['error'] is None and state['metadata']['input_kind'] == 'pdf'
assert state['summary']['extraction']['occurrence_count'] == 1
assert state['summary']['completed'] == 0
assert session.detail('pdf-ref-0001')['pdf']['fragments'][0]['page'] == 1
assert not Path('pdf-audit/cache').exists()
"""
    run([str(python), "-c", script], paper, env)
    assert source.read_bytes() == before
    invalid = paper / "invalid.pdf"
    invalid.write_bytes(b"not a PDF")
    result = subprocess.run(
        [str(executable), "verify", str(invalid), "--json"],
        cwd=paper,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "failed" and envelope["extraction"]["state"] == "failed"
    assert envelope["error"]["diagnostics"]
    assert not (paper / "invalid.bib-lint").exists()
