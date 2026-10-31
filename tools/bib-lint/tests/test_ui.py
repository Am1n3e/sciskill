"""Workflow and HTTP contracts for the packaged browser interface."""

import json
import threading

import httpx
import pytest
from provider_support import fixture_registry
from support import FakeClient

from bib_lint.audit import Workspace, run_audit
from bib_lint.storage import write_json
from bib_lint.verification.cache import ResponseCache
from bib_lint.viewer.app import ViewerSession
from bib_lint.viewer.jobs import ACTIVE, Job, command_for
from bib_lint.viewer.server import make_server


class UIRegistry:
    def __init__(self):
        self.jobs = {}
        self.starts = []
        self.stops = []

    def find(self, root, owner=None):
        return self.jobs.get(str(root))

    def start(self, source, *, output=None, owner, **options):
        if any(job.state in ACTIVE for job in self.jobs.values()):
            raise ValueError("already running")
        workspace, _, _ = run_audit(source, output=output, aux=options.get("aux"), preview=True)
        self.starts.append(options)
        job = Job(workspace, command_for(source, workspace, **options), {owner})
        self.jobs[str(workspace.root)] = job
        return job

    def stop(self, job):
        self.stops.append(job.id)
        job.state = "stopping"

    def shutdown(self):
        pass


@pytest.fixture
def registry():
    return UIRegistry()


@pytest.fixture
def ui(registry):
    return ViewerSession(registry)


@pytest.fixture
def browser(registry):
    with make_server(registry=registry) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            yield client
        server.shutdown()
        thread.join(timeout=3)


def post(client, **payload):
    token = client.get("/api/state").json()["csrf"]
    return client.post("/api/action", json=payload, headers={"X-CSRF-Token": token})


def test_empty_startup_invalid_paths_and_parse_scope(ui, tmp_path):
    assert ui.state()["summary"] is None
    with pytest.raises(ValueError, match="local bibliography"):
        ui.action({"action": "parse"})
    bib = tmp_path / "refs.bib"
    bib.write_text("@book{A,title={One}}\n@book{B,title={Two}}")
    aux = tmp_path / "paper.aux"
    aux.write_text(r"\citation{A,missing}")
    state = ui.action({"action": "parse", "bibliography": str(bib), "aux": str(aux)})
    report = json.loads((tmp_path / "refs.bib-lint/report.tmp.json").read_text())
    assert report["verification_scope"]["eligible_keys"] == ["A"]
    assert "verification_run" not in report
    assert any("missing" in w for w in state["warnings"])
    assert state["summary"]["completed"] == 0 and state["summary"]["eligible"] == 1
    assert not (tmp_path / "refs.bib-lint/cache").exists()


def test_unknown_usage_and_checkpoint_reload(ui, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@book{A,title={One}}\n@book{B,title={Two}}")
    workspace, report, _ = run_audit(bib, preview=True)
    state = ui.action({"action": "open", "report": str(workspace.root)})
    assert state["summary"]["used"] is None and state["summary"]["eligible"] == 2
    assert state["summary"]["skipped"] == 0
    report["items"][0]["validations"]["correctness"] = {
        "complete": True,
        "is_correct": True,
        "methods": [],
    }
    write_json(workspace.checkpoint, report)
    assert ui.state()["summary"]["completed"] == 1


def test_verify_stop_resume_and_refresh(ui, registry, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@book{A,title={One}}")
    state = ui.action({"action": "verify", "bibliography": str(bib)})
    assert state["job"]["state"] == "running" and len(registry.starts) == 1
    assert ui.detail("A")["entry"]["key"] == "A"
    assert ui.state()["job"]["state"] == "running" and len(registry.starts) == 1
    with pytest.raises(ValueError, match="already running"):
        ui.action({"action": "parse", "bibliography": str(bib)})
    job = next(iter(registry.jobs.values()))
    ui.action({"action": "stop"})
    assert registry.stops == [job.id] and job.state == "stopping"
    with pytest.raises(ValueError, match="Wait"):
        ui.action({"action": "resume"})
    job.state = "interrupted"
    ui.action({"action": "resume"})
    assert len(registry.starts) == 2 and not registry.starts[-1].get("refresh")
    job = next(iter(registry.jobs.values()))
    job.state = "completed"
    ui.action({"action": "refresh_key", "bibliography": str(bib), "key": "a"})
    assert registry.starts[-1]["refresh"] and registry.starts[-1]["citation_key"] == "a"
    job = next(iter(registry.jobs.values()))
    job.state = "interrupted"
    ui.action({"action": "resume"})
    assert not registry.starts[-1].get("refresh") and registry.starts[-1]["citation_key"] == "a"


def test_saved_resume_and_new_session_reattaches(ui, registry, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@book{A,title={One}}\n@book{B,title={Two}}")
    aux = tmp_path / "paper.aux"
    aux.write_text(r"\citation{A}")
    workspace, _, _ = run_audit(bib, aux=aux, preview=True)
    ui.action({"action": "open", "report": str(workspace.root)})
    ui.action({"action": "resume"})
    assert registry.starts[-1]["aux"] == str(aux)
    other = ViewerSession(registry, workspace.root)
    assert other.state()["job"]["state"] == "running"
    assert len(registry.starts) == 1
    before = workspace.checkpoint.read_bytes()
    with pytest.raises(ValueError, match="unused"):
        run_audit(bib, aux=aux, citation_key="B", client=FakeClient(), methods=fixture_registry({}))
    assert workspace.checkpoint.read_bytes() == before


def test_launch_failure_visible_without_report(ui, registry, tmp_path, monkeypatch):
    def fail(source, *, output=None, owner, **options):
        workspace = Workspace.for_input(source, output)
        job = Job(
            workspace,
            command_for(source, workspace, **options),
            {owner},
            state="failed",
            error="Could not launch",
        )
        registry.jobs[str(workspace.root)] = job
        return job

    monkeypatch.setattr(registry, "start", fail)
    state = ui.action({"action": "verify", "bibliography": str(tmp_path / "missing.bib")})
    assert state["job"]["error"] == "Could not launch"
    assert state["job"]["state"] == "failed"


@pytest.mark.parametrize(
    "content_type,raw",
    [
        ("application/json", b'{"saved": true}'),
        ("application/xml", b"<feed><title>Saved response</title></feed>"),
        ("text/html", b"<html><script>alert('raw')</script>Saved response</html>"),
    ],
)
def test_cached_responses_and_integrity(ui, tmp_path, content_type, raw):
    bib = tmp_path / "refs.bib"
    bib.write_text("@book{A,title={One}}")
    workspace, _, _ = run_audit(bib, preview=True)
    entry = ResponseCache(workspace.cache).save(
        "A",
        "publisher",
        "request",
        "https://jmlr.org/paper",
        httpx.Response(200, content=raw, headers={"Content-Type": content_type}),
    )
    ui.action({"action": "open", "report": str(workspace.root)})
    assert len(ui.detail("A")["responses"]) == 1
    result = ui.response("A", 0)
    assert result["verified"] is True
    expected = "saved" if content_type == "application/json" else "Saved response"
    assert expected in result["text"]
    path = workspace.cache / entry["path"]
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="Checksum"):
        ui.response("A", 0)
    assert path.read_bytes() == b"corrupted"
    with pytest.raises(ValueError, match="not found"):
        ui.response("A", 99)


def test_http_assets_and_read_api(browser, tmp_path):
    page = browser.get("/")
    assert page.status_code == 200
    assert "SciSkill" in page.text and "BibLint" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert browser.get("/app.js").status_code == browser.get("/styles.css").status_code == 200
    assert browser.get("/api/state").json()["summary"] is None
    assert browser.get("/references.json").status_code == 404
    bib = tmp_path / "refs.bib"
    bib.write_text('@book{A,title={Text <script>alert("raw")</script>}}')
    state = post(browser, action="parse", bibliography=str(bib)).json()
    assert state["summary"]["total"] == 1
    assert browser.get("/api/reference", params={"key": "A"}).json()["entry"]["key"] == "A"
    assert browser.get("/api/reference", params={"key": "missing"}).status_code == 422
    assert browser.get("/api/state").headers["cache-control"] == "no-store"
    assert browser.get("/api/state", headers={"Host": "evil.example"}).status_code == 403


def test_results_are_the_default_page_without_overview_navigation(browser):
    from bs4 import BeautifulSoup

    page = BeautifulSoup(browser.get("/").text, "html.parser")
    assert page.h1.get_text(" ", strip=True) == "SciSkill / BibLint"
    references = page.select_one("#references-panel")
    assert references is not None and not references.has_attr("hidden")
    assert references.select_one("#references-table") is not None
    assert not page.select("[role=tablist], #overview-panel, #overview-tab")
    assert page.select_one("#input-summary") is not None
    assert page.select_one("#run-summary") is not None


def test_audit_summary_is_a_table_without_the_read_only_label(browser):
    from bs4 import BeautifulSoup

    page = BeautifulSoup(browser.get("/").text, "html.parser")
    summary = page.select_one('table[aria-label="Audit summary"]')
    assert summary is not None
    assert summary.select_one("#input-summary th").get_text(strip=True) == "Input"
    assert [th.get_text(strip=True) for th in summary.select("#run-summary th")] == [
        "References",
        "Processed references",
        "Valid",
        "Invalid",
        "Unresolved",
    ]
    assert "Read-only" not in page.get_text()
    assert page.select_one("#access-mode") is None


def test_http_write_boundaries(browser, tmp_path):
    token = browser.get("/api/state").json()["csrf"]
    assert browser.post("/api/action", json={"action": "parse"}).status_code == 403
    headers = {"X-CSRF-Token": token}
    assert browser.post("/api/action", json={"action": "parse"}, headers=headers).status_code == 422
    assert (
        browser.post(
            "/api/action",
            json={"action": "parse"},
            headers={**headers, "Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    assert (
        browser.post("/api/action", json={"action": ["parse"]}, headers=headers).status_code == 422
    )
    assert (
        browser.post("/api/action", json={"action": "anything"}, headers=headers).status_code == 422
    )
    assert browser.post("/api/other", json={}, headers=headers).status_code == 404


def test_http_sessions_keep_independent_selection(browser, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@book{A,title={One}}")
    assert post(browser, action="parse", bibliography=str(bib)).status_code == 200
    first = browser.get("/api/state").json()
    cookie = httpx.Cookies(browser.cookies)
    browser.cookies.clear()
    second = browser.get("/api/state").json()
    assert second["report_path"] == "" and first["csrf"] != second["csrf"]
    browser.cookies = cookie
    assert browser.get("/api/state").json()["report_path"] == first["report_path"]


def test_invalid_paths_and_unknown_detail(ui, tmp_path):
    with pytest.raises(OSError):
        ui.action({"action": "open", "report": str(tmp_path / "missing")})
    with pytest.raises(ValueError, match="Unknown audit action"):
        ui.action({"action": "anything"})
    with pytest.raises(ValueError, match="No running audit"):
        ui.action({"action": "stop"})
    bib = tmp_path / "empty.bib"
    bib.write_text("%empty")
    workspace, _, _ = run_audit(bib, preview=True)
    ui.action({"action": "open", "report": str(workspace.root)})
    assert ui.state()["summary"]["total"] == 0
    with pytest.raises(ValueError, match="key not found"):
        ui.detail("missing")


def test_generic_provider_revision_and_scope(ui, tmp_path):
    from provider_support import FixtureProvider

    from bib_lint.verification.providers import METHODS
    from bib_lint.verification.providers.protocol import LookupAttempt, LookupResult

    bib = tmp_path / "refs.bib"
    bib.write_text("@article{Example,title={An Example Paper},author={Jane Smith},year={2025}}")
    payload = {
        "heading": "An Example Paper",
        "people": [{"given": "Jane", "family": "Smith"}],
        "date": "2025",
    }
    providers = [FixtureProvider(name, payload=payload) for name in METHODS]

    def incomplete(*_):
        return LookupResult(
            attempts=(LookupAttempt("catalog", "volume 2025", complete=False),),
            complete=False,
            diagnostic="Page budget exhausted",
        )

    providers.append(FixtureProvider("extension", version="2", lookup=incomplete))
    workspace, _, _ = run_audit(bib, methods=providers, client=FakeClient())
    ui.action({"action": "open", "report": str(workspace.root)})
    detail = ui.detail("Example")
    assert {row["Source"] for row in detail["sources"]} == set(METHODS) | {"extension"}
    extension = next(row for row in detail["sources"] if row["Source"] == "extension")
    assert extension["Revision"] == "2" and extension["Search scope"] == "volume 2025"
    assert extension["Error"] == "Page budget exhausted"
    assert "incomplete_search" in json.dumps(detail["methods"])
