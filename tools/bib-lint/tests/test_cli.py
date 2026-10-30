import json
from pathlib import Path

import httpx
import pytest
from provider_support import fixture_registry
from support import FakeClient

from bib_lint.audit import run_audit
from bib_lint.cli import main
from bib_lint.storage import report_lock
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.matching import select_result
from bib_lint.verification.providers import METHODS


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / "refs.bib"
    path.write_text("@book{A,title={One},author={Jane Smith},year={2025}}\n@book{B,title={Two}}")

    def run(*args, **kwargs):
        kwargs["client"] = FakeClient()
        kwargs["methods"] = fixture_registry(
            {"test": lambda r, c: select_result("test", r, [r], authority=True)}
        )
        return run_audit(*args, **kwargs)

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    return path


def result(capsys):
    streams = capsys.readouterr()
    return json.loads(streams.out), streams.err


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_help_version(option, capsys):
    with pytest.raises(SystemExit) as exc:
        main([option])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "bib-lint" in output
    if option == "--help":
        assert "{verify,view}" in output and "{parse," not in output


@pytest.mark.parametrize(
    "args", [[], ["parse", "x.bib"], ["verify"], ["verify", "x.bib", "--bogus"], ["unknown"]]
)
def test_json_argument_errors(args, capsys):
    assert main([*args, "--json"]) == 2
    envelope, err = result(capsys)
    assert envelope["status"] == "failed" and envelope["error"]["code"] == "arguments"
    assert envelope["summary"] is None and envelope["scope"] is None
    assert err.startswith("Error:")
    if args and args[0] == "parse":
        assert "verify" in err and "parse_bib" in err


def test_json_complete_and_partial_streams(source, capsys):
    assert main(["verify", str(source), "--key", "a", "--json", "--verbose"]) == 0
    envelope, err = result(capsys)
    assert set(envelope) == {
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
    assert envelope["status"] == "partial" and not envelope["complete"]
    assert envelope["summary"]["pending"] == 1 and envelope["summary"]["used"] is None
    assert envelope["report_path"] is None
    assert Path(envelope["checkpoint_path"]).is_absolute()
    assert "Fetching" in err
    assert main(["verify", str(source), "--json"]) == 0
    envelope, err = result(capsys)
    assert envelope["status"] == "completed" and envelope["complete"]
    assert envelope["checkpoint_path"] is None and Path(envelope["report_path"]).exists()
    assert "Resumed" in err


def test_aux_warning_and_human_summary(source, tmp_path, capsys):
    aux = tmp_path / "paper.aux"
    aux.write_text(r"\citation{A,missing}")
    assert main(["verify", str(source), "--aux", str(aux)]) == 0
    streams = capsys.readouterr()
    assert "scope: used" in streams.out and "source failures:" in streams.out
    assert "Missing citation keys: missing" in streams.err
    assert "Fetching" not in streams.out


@pytest.mark.parametrize("flag", ["--aux", "--encoding", "--include-source"])
def test_json_parse_options_rejected(source, tmp_path, capsys, flag):
    run_audit(source, preview=True)
    path = source.with_name("refs.bib-lint") / "report.tmp.json"
    args = ["verify", str(path), "--json", "-o", str(tmp_path / "import"), flag]
    if flag != "--include-source":
        args.append("utf-8")
    assert main(args) == 2
    envelope, _ = result(capsys)
    assert "only to bibliography" in envelope["error"]["message"]
    assert not (tmp_path / "import").exists()


def test_provider_failure_exit_zero_and_invalid_key_unchanged(source, monkeypatch, capsys):
    def fail(*_):
        raise RuntimeError("provider down")

    def run(*args, **kwargs):
        return run_audit(
            *args, **kwargs, client=FakeClient(), methods=fixture_registry({"test": fail})
        )

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    assert main(["verify", str(source), "--json"]) == 0
    envelope, _ = result(capsys)
    assert envelope["summary"]["source_failures"] == 2
    final = Path(envelope["report_path"])
    before = final.read_bytes()
    assert main(["verify", str(source), "--key", "missing", "--json"]) == 2
    assert result(capsys)[0]["status"] == "failed"
    assert final.read_bytes() == before


def test_interrupt_and_write_failure_outputs(source, monkeypatch, capsys):
    def interrupted(*_):
        raise KeyboardInterrupt

    def run(*args, **kwargs):
        return run_audit(
            *args, **kwargs, client=FakeClient(), methods=fixture_registry({"test": interrupted})
        )

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    assert main(["verify", str(source), "--json"]) == 130
    envelope, _ = result(capsys)
    assert envelope["status"] == "interrupted" and Path(envelope["checkpoint_path"]).exists()

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr("bib_lint.verification._write_json", fail)
    assert main(["verify", str(source), "--json"]) == 2
    envelope, _ = result(capsys)
    assert not envelope["complete"] and envelope["status"] == "failed"


def test_invalid_input_no_artifacts(tmp_path, capsys):
    source = tmp_path / "missing.bib"
    assert main(["verify", str(source), "--json"]) == 2
    envelope, _ = result(capsys)
    assert envelope["report_path"] is envelope["checkpoint_path"] is None
    assert not Path(envelope["output_dir"]).exists()


def test_view_launch_port_failure_and_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "bib_lint.viewer.server.serve", lambda *args, **kw: calls.append((args, kw))
    )
    assert main(["view", "--port", "9001", "--no-browser"]) == 0
    assert calls == [(("", 9001), {"no_browser": True})]
    assert main(["view", "--port", "0"]) == 2

    def fail(*args, **kwargs):
        raise OSError("Port unavailable")

    monkeypatch.setattr("bib_lint.viewer.server.serve", fail)
    assert main(["view"]) == 2

    def stop(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("bib_lint.viewer.server.serve", stop)
    assert main(["view"]) == 130


def test_encoding_source_include_and_output_alias(source, tmp_path, capsys):
    source.write_bytes("@book{A,title={Café}}".encode("latin-1"))
    assert main(["verify", str(source), "--encoding", "latin-1", "--include-source", "--json"]) == 0
    envelope, _ = result(capsys)
    report = json.loads(Path(envelope["report_path"]).read_text())
    assert report["source_text"] == "@book{A,title={Café}}"
    assert main(["verify", str(source), "--output", str(source), "--json"]) == 2
    assert result(capsys)[0]["status"] == "failed"


def test_lock_error_and_secret_redaction(source, monkeypatch, capsys):
    from bib_lint.audit import Workspace
    from bib_lint.storage import report_lock

    workspace = Workspace.for_input(source)
    workspace.root.mkdir()
    with report_lock(workspace.final):
        assert main(["verify", str(source), "--json"]) == 2
    envelope, _ = result(capsys)
    assert "already in use" in envelope["error"]["message"]
    monkeypatch.setenv("OPENALEX_API_KEY", "VERYSECRET")

    def fail(*_, **__):
        raise ValueError("Failed with VERYSECRET")

    monkeypatch.setattr("bib_lint.cli.run_audit", fail)
    assert main(["verify", str(source), "--json"]) == 2
    envelope, err = result(capsys)
    assert "VERYSECRET" not in json.dumps(envelope) + err


def test_cache_lock_failure_json_is_failed_and_resumable(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "references.bib"
    original = (
        "@article{A,title={An Example Paper},author={Smith, Jane},year={2025},"
        "journal={Example Journal},url={https://proceedings.mlr.press/v267/example25a.html}}"
    )
    bib.write_text(original)
    output = tmp_path / "audit"
    cache = output / "cache"
    cache.mkdir(parents=True)
    calls = []
    body = (Path(__file__).parent / "fixtures/providers/publication.html").read_text()
    client = MetadataClient(
        cache,
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, text=body)),
    )

    def run(*args, **kwargs):
        return run_audit(*args, **kwargs, client=client, methods=[METHODS["pmlr"]])

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    try:
        with report_lock(cache / "checksum.json"):
            assert main(["verify", str(bib), "--output", str(output), "--json"]) == 2
        envelope, err = result(capsys)
        assert envelope["status"] == "failed" and not envelope["complete"]
        assert envelope["error"]["code"] == "audit_failed" and "already in use" in err
        assert envelope["summary"]["source_failures"] == 0
        assert envelope["report_path"] is None and Path(envelope["checkpoint_path"]).exists()
        assert not calls
        assert main(["verify", str(bib), "--output", str(output), "--json"]) == 0
        envelope, _ = result(capsys)
        assert envelope["complete"] and envelope["summary"]["correct"] == 1
        assert len(calls) == 1 and bib.read_text() == original
    finally:
        client.close()


def test_source_failure_warning_survives_resume_and_partial_output(tmp_path, capsys, monkeypatch):
    path = tmp_path / "refs.bib"
    path.write_text("@book{A,title={One}}\n@book{B,title={Two}}")
    calls = []

    def fail(record, client):
        calls.append(record["title"])
        raise ValueError("Provider unavailable")

    def run(*args, **kwargs):
        return run_audit(
            *args, **kwargs, client=FakeClient(), methods=fixture_registry({"test": fail})
        )

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    assert main(["verify", str(path), "--key", "A", "--json"]) == 0
    envelope, err = result(capsys)
    assert not envelope["complete"]
    assert "1 source lookups failed" in envelope["warnings"][0]
    assert "--refresh" in err
    assert main(["verify", str(path), "--json"]) == 0
    envelope, _ = result(capsys)
    assert envelope["complete"] and envelope["summary"]["source_failures"] == 2
    assert calls == ["One", "Two"]
