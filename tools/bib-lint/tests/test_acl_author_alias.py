"""Display aliases in primary HTML are not citation family names."""

from contextlib import closing
from pathlib import Path

import httpx
import pytest

from bib_lint.parser import parse_string
from bib_lint.verification import verify_reference
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS

URL = "https://aclanthology.org/2024.acl-long.409/"
FIXTURE = Path(__file__).parent / "fixtures/providers/acl-author-alias.html"
BIBTEX = r"""@inproceedings{trial,
 title={Trial and Error: Exploration-Based Trajectory Optimization of LLM Agents},
 author={Song, Yifan and Yin, Da and Yue, Xiang and Huang, Jie and Li, Sujian and Lin, Bill Yuchen},
 year={2024},
 booktitle={Proceedings of the 62nd Annual Meeting of the Association for
 Computational Linguistics (Volume 1: Long Papers)},
 doi={10.18653/v1/2024.acl-long.409},
 url={https://aclanthology.org/2024.acl-long.409/}
}"""


def test_acl_explicit_citation_does_not_misparse_the_display_alias_as_family(tmp_path):
    entry = parse_string(BIBTEX).to_dict()["items"][0]["entry"]
    calls = []

    def respond(request):
        calls.append(str(request.url))
        assert str(request.url) == URL
        return httpx.Response(200, text=FIXTURE.read_text())

    with closing(
        MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    ) as client:
        result = verify_reference(entry, client, methods=[METHODS["acl_anthology"]])
    method = result["methods"][0]
    assert method["found_ref"]["authors"][4] == {"given": "Sujian", "family": "Li", "suffix": ""}
    assert next(c for c in method["comparisons"] if c["field"] == "authors")["result"] == "match"
    assert result["is_correct"] is True
    assert calls == [URL]


@pytest.mark.parametrize("replacement", ["Li, David", "Wang, Sujian"])
def test_explicit_source_name_still_rejects_a_wrong_printed_author(tmp_path, replacement):
    entry = parse_string(BIBTEX.replace("Li, Sujian", replacement)).to_dict()["items"][0]["entry"]
    with closing(
        MetadataClient(
            tmp_path / "cache",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text=FIXTURE.read_text())),
        )
    ) as client:
        result = verify_reference(entry, client, methods=[METHODS["acl_anthology"]])
    assert result["is_correct"] is False
    assert any(
        c["field"] == "authors" and c["result"] == "mismatch"
        for c in result["methods"][0]["comparisons"]
    )


def test_old_acl_alias_verdict_recomputes_from_cached_primary_evidence(tmp_path):
    from bib_lint.audit import run_audit
    from bib_lint.storage import write_json

    source = tmp_path / "references.bib"
    source.write_text(BIBTEX)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=FIXTURE.read_text())

    output = tmp_path / "audit"
    with closing(
        MetadataClient(output / "cache", transport=httpx.MockTransport(respond))
    ) as client:
        workspace, report, _ = run_audit(
            source, output=output, client=client, methods=[METHODS["acl_anthology"]]
        )
        report["verification_run"]["providers"][0]["adapter_version"] = "2"
        method = report["items"][0]["validations"]["correctness"]["methods"][0]
        method["adapter_version"] = "2"
        method["found_ref"]["authors"][4] = {
            "given": "Sujian Li",
            "family": "(李素建)",
            "suffix": "",
        }
        report["items"][0]["validations"]["correctness"]["is_correct"] = False
        write_json(workspace.final, report)
        _, resumed, _ = run_audit(
            source, output=output, client=client, methods=[METHODS["acl_anthology"]]
        )
    result = resumed["items"][0]["validations"]["correctness"]
    assert result["is_correct"] is True
    assert result["methods"][0]["adapter_version"] == "3"
    assert result["methods"][0]["requests"][0]["cached"] is True
    assert calls == [URL]
