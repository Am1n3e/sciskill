"""Offline contracts for original inputs, honest scoring and resumable harnesses."""

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from evaluation import harness
from evaluation.benchmarks.common import digest
from evaluation.benchmarks.conversion import make_report, parse_raw_reference
from evaluation.benchmarks.scoring import (
    binary_metrics,
    check_official_evaluator,
    coverage,
    prediction_from_report,
    score,
)
from evaluation.benchmarks.sources import (
    BENCHMARKS,
    Case,
    load_appendix,
    load_cases,
    prepare,
    verify_snapshot,
)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def snapshot(root, name, files):
    folder = root / "sources" / name
    folder.mkdir(parents=True)
    for filename, content in files.items():
        (folder / filename).write_bytes(content)
    (folder / "snapshot.json").write_text(
        json.dumps(
            {
                **BENCHMARKS[name],
                "benchmark": name,
                "status": "ready",
                "files": {
                    f: {"sha256": digest(b), "url": "https://example.org/" + f}
                    for f, b in files.items()
                },
            }
        )
    )
    return folder


def hallmark_row(key, label="VALID", **kwargs):
    return {
        "bibtex_key": key,
        "bibtex_type": "article",
        "fields": {"title": "Unbalanced { title", "author": "Smith, A.", "year": "2024"},
        "label": label,
        "hallucination_type": "swapped_authors" if label == "HALLUCINATED" else None,
        "difficulty_tier": 2 if label == "HALLUCINATED" else None,
        **kwargs,
    }


def zenodo_rows():
    return [
        {
            "document_id": "P1",
            "reference_number": f"R{i}",
            "manual_label": label,
            "reference": f"A. Smith. Paper {i}. Journal, 2024.",
        }
        for i, label in enumerate(["verified", "problematic", "problematic"], 1)
    ]


def test_benchmark_module_commands_use_frozen_local_inputs(tmp_path):
    snapshot(
        tmp_path, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(zenodo_rows())}
    )
    for command in ("prepare", "score"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "evaluation.harness",
                command,
                "--benchmark",
                "zenodo",
                "--root",
                str(tmp_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        value = json.loads(result.stdout)["zenodo"]
        if command == "prepare":
            assert value["status"] == "ready"
        else:
            assert value["all"]["coverage"]["official_cases"] == 3


def report(key="a", verdict=None, status="not_found", *, complete=True):
    return {
        "items": [
            {
                "entry": {"key": key},
                "validations": {
                    "correctness": {
                        "is_correct": verdict,
                        "complete": complete,
                        "methods": [
                            {
                                "name": "arxiv",
                                "status": status,
                                **(
                                    {"error": {"code": "timeout", "message": "Unavailable"}}
                                    if status == "error"
                                    else {}
                                ),
                            }
                        ],
                    }
                },
            }
        ]
    }


def test_original_hallmark_fields_duplicates_and_malformed_tex_retained(tmp_path):
    rows = [hallmark_row("a"), hallmark_row("b", "HALLUCINATED"), hallmark_row("__canary__marker")]
    snapshot(
        tmp_path,
        "hallmark",
        {"dev_public.jsonl": "".join(json.dumps(r) + "\n" for r in rows).encode()},
    )
    cases = load_cases("hallmark", "dev_public", tmp_path)
    assert [c.id for c in cases] == ["a", "b"]
    assert [c.issue for c in cases] == [False, True]
    for case in cases:
        converted, provenance = make_report(case)
        assert provenance["fields"] == case.original["fields"]
        assert converted["items"][0]["entry"]["fields"]["title"] == "Unbalanced { title"
        assert "label" not in converted and "issue" not in converted
        assert converted["verification_scope"]["eligible_keys"] == [case.id]


def test_official_csv_preserves_rows_labels_and_encoding(tmp_path):
    rows = zenodo_rows()
    rows[0]["reference"] = "M. Ram‚. Unmodified text. Journal, 2024."
    snapshot(tmp_path, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(rows)})
    cases = load_cases("zenodo", "all", tmp_path)
    assert [c.original for c in cases] == rows
    assert [c.issue for c in cases] == [False, True, True]
    assert cases[0].raw_reference == rows[0]["reference"]
    with pytest.raises(ValueError, match="Unknown split"):
        load_cases("zenodo", "invented", tmp_path)


def test_source_download_frozen_and_checksum_verified(tmp_path):
    calls = []
    content = csv_bytes([{"Published Paper": "Paper", "Example of Verified Hallucination": "Raw"}])

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=content, headers={"content-type": "text/csv"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        manifest = prepare("gptzero", tmp_path, client)
        assert prepare("gptzero", tmp_path, client) == manifest
    assert len(calls) == 1
    assert manifest["retrieved_at"]
    assert load_cases("gptzero", "all", tmp_path)[0].raw_reference == "Raw"
    path = tmp_path / "sources" / "gptzero" / "references.csv"
    path.write_bytes(content + b"changed")
    with pytest.raises(ValueError, match="snapshot changed"):
        verify_snapshot(path.parent)


def test_html_is_not_silently_saved_as_dataset(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, text="<html>Blocked</html>", headers={"content-type": "text/html"}
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="received HTML"):
            prepare("gptzero", tmp_path, client)
    assert not (tmp_path / "sources" / "gptzero" / "snapshot.json").exists()


@pytest.mark.parametrize(
    ("raw", "title", "author", "year"),
    [
        (
            "Smith, A., & Doe, B. (2024). A paper. Journal.",
            "A paper",
            "Smith, A. and Doe, B.",
            "2024",
        ),
        (
            "A. Smith and B. Doe. A paper. In Proceedings of a Conference, 2024.",
            "A paper",
            "A. Smith and B. Doe",
            "2024",
        ),
        ('A. Smith, "A paper", Journal, 2024.', "A paper", "A. Smith", "2024"),
        (
            "A. Smith et al. ?A paper?. en. In: Journal (June 2024). issn: 2052-4463.",
            "A paper",
            "A. Smith and others",
            "2024",
        ),
        (
            "Smith, A., Doe, B.C.: A paper. Journal 12 (2024)",
            "A paper",
            "Smith, A. and Doe, B.C.",
            "2024",
        ),
        ("A. Smith.A paper. Journal, 2024.", "A paper", "A. Smith", "2024"),
        ("Team. (2024). A paper. https://example.org/x", "A paper", "{Team}", "2024"),
    ],
)
def test_raw_format_adapters(raw, title, author, year):
    _, fields = parse_raw_reference(raw)
    assert (fields["title"], fields["author"], fields["year"]) == (title, author, year)


def test_conversion_does_not_repair_venue_or_drop_corporate_author():
    _, fields = parse_raw_reference(
        'A. Smith. "A paper". In: Journal (2024). URL: https://arxiv.org/abs/2401.01234.'
    )
    assert fields["journal"] == "Journal" and fields["eprint"] == "2401.01234"
    _, fields = parse_raw_reference("Team, Smith, A., ? Doe, B. (2024). A paper.")
    assert fields["author"] == "{Team} and Smith, A. and ? Doe, B."
    assert "others" not in fields["author"]
    _, fields = parse_raw_reference("A. Smith. A paper. Journal.")
    assert "year" not in fields
    with pytest.raises(ValueError, match="boundary"):
        parse_raw_reference("Unrecognized citation")


@pytest.mark.parametrize(
    ("verdict", "status", "complete", "label", "evaluated", "flagged"),
    [
        (True, "found", True, "VALID", True, False),
        (False, "found", True, "HALLUCINATED", True, True),
        (None, "not_found", True, "UNCERTAIN", True, True),
        (None, "error", True, "UNCERTAIN", False, None),
        (None, "found", False, "UNCERTAIN", False, None),
    ],
)
def test_prediction_mapping_keeps_failures_and_uncertainty_distinct(
    verdict, status, complete, label, evaluated, flagged
):
    prediction = prediction_from_report(report(verdict=verdict, status=status, complete=complete))
    assert (prediction["label"], prediction["evaluated"], prediction["flagged"]) == (
        label,
        evaluated,
        flagged,
    )


def test_binary_scores_use_full_denominator_and_missing_cases_block_metrics():
    cases = [
        Case(str(i), "zenodo", "all", {}, truth)
        for i, truth in enumerate([True, True, False, False])
    ]
    predictions = [
        prediction_from_report(report(str(i), verdict=not flag, status="found"))
        for i, flag in enumerate([True, False, True, False])
    ]
    aligned, counts = coverage(cases, predictions)
    metrics = binary_metrics(cases, aligned)
    assert counts["evaluated"] == 4
    assert metrics == {
        "tp": 1,
        "fp": 1,
        "tn": 1,
        "fn": 1,
        "accuracy": 0.5,
        "precision": 0.5,
        "recall": 0.5,
        "false_positive_rate": 0.5,
        "f1": 0.5,
    }
    aligned, counts = coverage(cases, predictions[:1])
    assert counts["official_cases"] == 4 and counts["attempted"] == 1
    assert binary_metrics(cases, aligned) is None
    with pytest.raises(ValueError, match="duplicate or unknown"):
        coverage(cases, [predictions[0], predictions[0]])


def test_positive_only_collection_does_not_claim_accuracy(tmp_path):
    cases = [Case(str(i), "gptzero", "all", {}, True) for i in range(2)]
    prediction = prediction_from_report(report("0", verdict=False, status="found"))
    result = score("gptzero", "all", cases, [prediction], tmp_path, tmp_path)
    assert result["collection_summary"]["flagged_fraction_of_full_collection"] == 0.5
    assert result["coverage"]["official_cases"] == 2 and not result["complete"]
    assert "protocol_metrics" not in result and "official_metrics" not in result


def test_official_evaluator_exports_exact_predictions_and_both_modes(tmp_path):
    pytest.importorskip("hallmark")
    from dataclasses import asdict

    from hallmark.dataset.schema import Prediction, load_entries
    from hallmark.evaluation.metrics import evaluate

    rows = [hallmark_row("a"), hallmark_row("b", "HALLUCINATED"), hallmark_row("c", "HALLUCINATED")]
    folder = snapshot(
        tmp_path,
        "hallmark",
        {"dev_public.jsonl": "".join(json.dumps(r) + "\n" for r in rows).encode()},
    )
    cases = load_cases("hallmark", "dev_public", tmp_path)
    predictions = [
        prediction_from_report(report("a", True, "found")),
        prediction_from_report(report("b", None, "not_found")),
    ]
    output = tmp_path / "out"
    output.mkdir()
    result = score("hallmark", "dev_public", cases, predictions, output, folder)
    official = [
        Prediction.from_dict(json.loads(line))
        for line in (output / "official_predictions.jsonl").read_text().splitlines()
    ]
    expected = evaluate(
        load_entries(folder / "dev_public.jsonl"),
        official,
        tool_name="bib-lint",
        split_name="dev_public",
        eval_mode="both",
    )
    for mode, value in expected.items():
        # Provenance added by the harness; all actual upstream metric fields match.
        actual = result["official_metrics"][mode]
        for key, metric in asdict(value).items():
            if key not in {"split_sha256", "source_condition", "tool_version", "run_timestamp"}:
                assert actual[key] == metric
    assert len(official) == 3 and not official[-1].evaluated
    assert result["coverage"]["definitive"] == 1
    assert result["supplementary_conservative_accuracy"] == 1.0


def test_wrong_evaluator_revision_rejected(monkeypatch):
    class WrongVersion:
        def read_text(self, _):
            return json.dumps({"vcs_info": {"commit_id": "unrelated"}})

    monkeypatch.setattr(
        "evaluation.benchmarks.scoring.importlib.metadata.distribution", lambda _: WrongVersion()
    )
    with pytest.raises(ValueError, match="revision differs"):
        check_official_evaluator()


def test_resume_retry_and_failed_inputs_stay_in_denominator(tmp_path):
    rows = zenodo_rows()
    rows[2]["reference"] = "Unknown format"
    snapshot(tmp_path, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(rows)})
    called = []
    refreshes = []

    def audit(path, **kwargs):
        key = json.loads(path.read_text())["items"][0]["entry"]["key"]
        called.append(key)
        refreshes.append(kwargs["refresh"])
        kwargs["progress"]("Fake provider")
        return (
            None,
            report(
                key,
                True if key.endswith("R1") else None,
                "found" if key.endswith("R1") else "error",
            ),
            [],
        )

    first = harness.run_split("zenodo", "all", tmp_path, limit=1, audit=audit, client=object())
    assert first["coverage"]["attempted"] == 1 and first["protocol_metrics"] is None
    result = harness.run_split("zenodo", "all", tmp_path, audit=audit, client=object())
    assert called == ["P1_R1", "P1_R2"] and result["complete"]
    assert result["coverage"]["evaluated"] == 1 and result["coverage"]["official_cases"] == 3
    harness.run_split("zenodo", "all", tmp_path, audit=audit, client=object())
    assert len(called) == 2
    harness.run_split("zenodo", "all", tmp_path, retry_errors=True, audit=audit, client=object())
    assert called[-1] == "P1_R2" and len(called) == 3
    assert refreshes == [False, False, True]
    predictions = harness.read_predictions(tmp_path / "runs" / "zenodo" / "all")
    assert len(predictions) == 3 and predictions[-1]["status"] == "Not evaluated"
    result_rows = list(
        csv.DictReader(
            (tmp_path / "runs" / "zenodo" / "all" / "official_format_results.csv").open()
        )
    )
    assert [r["bib_lint"] for r in result_rows] == ["not_flagged", "not_evaluated", "not_evaluated"]


def test_changed_tool_rejects_resume_and_interrupt_keeps_completed_cases(tmp_path, monkeypatch):
    snapshot(
        tmp_path, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(zenodo_rows())}
    )

    def audit(path, **_):
        key = json.loads(path.read_text())["items"][0]["entry"]["key"]
        if key.endswith("R2"):
            raise KeyboardInterrupt
        return None, report(key, True, "found"), []

    with pytest.raises(KeyboardInterrupt):
        harness.run_split("zenodo", "all", tmp_path, audit=audit, client=object())
    folder = tmp_path / "runs" / "zenodo" / "all"
    assert [p["id"] for p in harness.read_predictions(folder)] == ["P1_R1"]
    monkeypatch.setattr(harness, "tool_identity", lambda: {"changed": True})
    with pytest.raises(ValueError, match="fresh --root"):
        harness.run_split("zenodo", "all", tmp_path, audit=audit, client=object())


def appendix_html():
    rows = "".join(
        f"<tr><td>{'\\endlastfoot ' if i == 1 else ''}{i}</td><td>acl-2025</td>"
        f"<td>2025.acl-long.{i}</td><td>Example et al.</td>"
        f"<td>Alice Smith and Bob Doe. 2024b. A paper {i}. In Proceedings of ACL.</td></tr>"
        for i in range(1, 296)
    )
    return ("<table><tr><th>Example of HalluCitation</th></tr>" + rows + "</table>").encode()


def test_published_appendix_retains_every_numbered_reference(tmp_path):
    content = appendix_html()
    rows = load_appendix(content)
    assert len(rows) == 295 and rows[0]["row_number"] == 1 and rows[-1]["row_number"] == 295
    snapshot(tmp_path, "hallucitation", {"appendix.html": content})
    cases = load_cases("hallucitation", "all", tmp_path)
    assert len(cases) == 295 and all(c.issue for c in cases)
    report, conversion = make_report(cases[0])
    assert conversion["fields"] == {
        "title": "A paper 1",
        "author": "Alice Smith and Bob Doe",
        "year": "2024",
        "booktitle": "Proceedings of ACL",
    }
    assert report["items"][0]["entry"]["key"] == "hallucitation_001"
    with pytest.raises(ValueError, match="retain rows"):
        load_appendix(content.replace(b"\\endlastfoot 1", b"invalid"))
    with pytest.raises(ValueError, match="exactly one"):
        load_appendix(b"<html>Blocked</html>")


def test_appendix_prepare_accepts_real_html_but_validates_table(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=appendix_html(), headers={"content-type": "text/html"}
            )
        )
    ) as client:
        assert prepare("hallucitation", tmp_path, client)["status"] == "ready"
    assert len(load_cases("hallucitation", "all", tmp_path)) == 295


def test_appendix_multiple_examples_in_one_cell_are_both_run(tmp_path):
    content = appendix_html().replace(
        b"A paper 226. In Proceedings of ACL.",
        b"A paper 226. In Proceedings of ACL. X. Du et al. 2022b. Grit2: Another paper. "
        b"In Findings of EMNLP 2022.",
    )
    snapshot(tmp_path, "hallucitation", {"appendix.html": content})
    cases = load_cases("hallucitation", "all", tmp_path)
    assert len(cases) == 296
    double = [c for c in cases if c.original["row_number"] == 226]
    assert [c.id for c in double] == ["hallucitation_226_r1", "hallucitation_226_r2"]
    assert make_report(double[0])[1]["fields"]["title"] == "A paper 226"
    assert make_report(double[1])[1]["fields"]["title"] == "Grit2: Another paper"


def test_venue_conversion_keeps_volume_and_editors_separate():
    _, fields = parse_raw_reference(
        "A. Smith. A paper. In A. Editor (eds.), Proceedings of ACL, pages 10-20, 2024."
    )
    assert fields["booktitle"] == "Proceedings of ACL"
    _, fields = parse_raw_reference("A. Smith. A paper. Journal Name 10.2 (2024). doi: 10.1234/x")
    assert fields["journal"] == "Journal Name"
    assert (fields["volume"], fields["number"]) == ("10", "2")


def test_shared_host_pacer_and_transport_keep_policy_spacing():
    from evaluation.benchmarks.execution import HostPacer, PacedTransport

    clock = [0.0]
    calls = []

    def sleep(seconds):
        clock[0] += seconds

    pacer = HostPacer(clock=lambda: clock[0], sleep=sleep)
    transport = PacedTransport(
        pacer,
        httpx.MockTransport(
            lambda request: (
                calls.append((request.url.host, clock[0])) or httpx.Response(200, text="OK")
            )
        ),
    )
    transport.interval = 3.1
    with httpx.Client(transport=transport) as client:
        client.get("https://arxiv.org/a")
        client.get("https://arxiv.org/b")
        client.get("https://example.org/a")
        client.get("https://arxiv.org/c")
    assert calls == [
        ("arxiv.org", 0.0),
        ("arxiv.org", 3.1),
        ("example.org", 3.1),
        ("arxiv.org", 6.2),
    ]


def test_parallel_cases_use_isolated_clients_and_ordered_checkpoints(tmp_path):
    import threading

    snapshot(
        tmp_path, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(zenodo_rows())}
    )
    started = threading.Event()
    clients = []
    guard = threading.Lock()

    def audit(path, **kwargs):
        key = json.loads(path.read_text())["items"][0]["entry"]["key"]
        with guard:
            clients.append(kwargs["client"])
        if key.endswith("R1"):
            assert started.wait(3), "Cases did not overlap"
        else:
            started.set()
        assert kwargs["client"].cache_dir == kwargs["output"] / "cache"
        return None, report(key, True, "found"), []

    result = harness.run_split("zenodo", "all", tmp_path, workers=2, audit=audit)
    assert result["complete"] and result["coverage"]["evaluated"] == 3
    assert len({id(c) for c in clients}) == 3
    predictions = harness.read_predictions(tmp_path / "runs" / "zenodo" / "all")
    assert [p["id"] for p in predictions] == ["P1_R1", "P1_R2", "P1_R3"]
    assert all(c.client.is_closed for c in clients)


def test_real_tool_exception_recorded_and_remaining_cases_run(tmp_path):
    snapshot(
        tmp_path, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(zenodo_rows())}
    )

    def audit(path, **_):
        key = json.loads(path.read_text())["items"][0]["entry"]["key"]
        if key.endswith("R2"):
            raise RuntimeError("Genuine tool exception")
        return None, report(key, True, "found"), []

    result = harness.run_split("zenodo", "all", tmp_path, audit=audit, client=object())
    assert result["complete"] and result["coverage"]["attempted"] == 3
    predictions = harness.read_predictions(tmp_path / "runs" / "zenodo" / "all")
    assert predictions[1]["failure_stage"] == "bib_lint"


@pytest.mark.parametrize(
    "args", [["run", "--split", "x"], ["run", "--limit", "0"], ["score", "--limit", "1"]]
)
def test_cli_invalid_flags_fail_before_acquisition(args):
    with pytest.raises(SystemExit):
        harness.main(args)
