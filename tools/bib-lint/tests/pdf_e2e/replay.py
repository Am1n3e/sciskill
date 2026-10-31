"""Protocol-shaped scholarly responses built only from independently curated facts."""

import html
import re
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import httpx

HOSTS = {
    "proceedings.mlr.press": "pmlr",
    "jmlr.org": "jmlr",
    "www.jmlr.org": "jmlr",
    "aclanthology.org": "acl_anthology",
    "proceedings.neurips.cc": "neurips",
    "papers.nips.cc": "neurips",
    "api.openreview.net": "openreview",
    "api2.openreview.net": "openreview",
    "export.arxiv.org": "arxiv",
}


def _name(author):
    return " ".join(str(author.get(key) or "") for key in ("given", "family", "suffix")).strip()


def _meta(name, value):
    return f'<meta name="{name}" content="{html.escape(str(value or ""), quote=True)}">'


def _record_html(record):
    tags = [
        _meta("citation_title", record["title"]),
        _meta("citation_publication_date", record.get("year")),
        _meta("citation_journal_title", record.get("venue")),
    ]
    tags.extend(_meta("citation_author", _name(author)) for author in record.get("authors", []))
    if record.get("identifiers", {}).get("doi"):
        tags.append(_meta("citation_doi", record["identifiers"]["doi"]))
    return "<html><head>" + "".join(tags) + "</head><body></body></html>"


def _link(url, label):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(str(label))}</a>'


class ScholarlyReplay:
    """Only HTTP transport is replaced; providers/matching/consensus remain real."""

    def __init__(self, canonical):
        self.records = [
            dict(source["metadata"], provider=source["provider"]) for source in canonical.values()
        ]
        self.unexpected = []
        self.requests = []

    def __call__(self, request):
        self.requests.append(str(request.url))
        provider = HOSTS.get(request.url.host)
        if provider is None or request.method != "GET":
            self.unexpected.append(str(request.url))
            raise AssertionError(f"Unexpected scholarly request: {request.url}")
        records = [record for record in self.records if record["provider"] == provider]
        if provider == "arxiv":
            return self._arxiv(request, records)
        if provider == "openreview":
            return self._openreview(request, records)
        path = request.url.path
        record = next((record for record in records if urlsplit(record["url"]).path == path), None)
        if record:
            return httpx.Response(200, text=_record_html(record), request=request)
        content = self._catalog(provider, path, records)
        if content is None:
            self.unexpected.append(str(request.url))
            raise AssertionError(f"Unexpected scholarly route: {request.url}")
        return httpx.Response(
            200, text="<html><body>" + content + "</body></html>", request=request
        )

    def _arxiv(self, request, records):
        if request.url.path != "/api/query":
            self.unexpected.append(str(request.url))
            raise AssertionError(f"Unexpected arXiv route: {request.url}")
        identifier = request.url.params.get("id_list")
        if identifier:
            records = [
                r
                for r in records
                if r["identifiers"]["arxiv"] == identifier
                or (
                    not re.search(r"v\d+$", identifier)
                    and re.sub(r"v\d+$", "", r["identifiers"]["arxiv"]) == identifier
                )
            ]
        start = int(request.url.params.get("start", "0"))
        count = len(records)
        entries = []
        for record in records[start : start + 20]:
            authors = "".join(
                "<author><name>" + escape(_name(a)) + "</name></author>"
                for a in record.get("authors", [])
            )
            entries.append(
                "<entry><id>"
                + escape(record["url"])
                + "</id><title>"
                + escape(record["title"])
                + "</title><published>"
                + str(record["year"])
                + "-01-01T00:00:00Z</published>"
                + authors
                + "</entry>"
            )
        body = (
            '<feed xmlns="http://www.w3.org/2005/Atom" '
            'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
            f"<opensearch:totalResults>{count}</opensearch:totalResults>"
            + "".join(entries)
            + "</feed>"
        )
        return httpx.Response(200, text=body, request=request)

    def _openreview(self, request, records):
        if request.url.path not in {"/notes", "/notes/search"}:
            self.unexpected.append(str(request.url))
            raise AssertionError(f"Unexpected OpenReview route: {request.url}")
        identifier = request.url.params.get("id")
        if identifier:
            records = [r for r in records if r["identifiers"]["openreview"] == identifier]
        offset = int(request.url.params.get("offset", "0"))
        notes = []
        for record in records[offset : offset + 20]:
            venue = record.get("venue") or ""
            base = (
                "ICML.cc" if "ICML" in venue else "NeurIPS.cc" if "NeurIPS" in venue else "ICLR.cc"
            )
            accepted = record.get("publication_status") == "accepted"
            venueid = f"{base}/{record.get('year') or '2025'}/Conference"
            if not accepted:
                venueid += "/Submission"
            identifier = record["identifiers"]["openreview"]
            notes.append(
                {
                    "id": identifier,
                    "forum": identifier,
                    "content": {
                        "title": {"value": record["title"]},
                        "authors": {"value": [_name(a) for a in record.get("authors", [])]},
                        "year": {"value": record.get("year")},
                        "venue": {"value": record.get("venue")},
                        "venueid": {"value": venueid},
                    },
                }
            )
        return httpx.Response(200, json={"notes": notes, "count": len(records)}, request=request)

    def _catalog(self, provider, path, records):
        handlers = {
            "pmlr": self._pmlr_catalog,
            "jmlr": self._jmlr_catalog,
            "acl_anthology": self._acl_catalog,
            "neurips": self._neurips_catalog,
        }
        return handlers[provider](path, records)

    def _pmlr_catalog(self, path, records):
        if path == "/":
            return "".join(
                _link("/" + r["identifiers"]["pmlr"].split("/")[0] + "/", f"ICML {r['year']}")
                for r in records
            )
        if re.fullmatch(r"/v\d+/?", path):
            return "".join(
                _link(r["url"], r["title"])
                for r in records
                if urlsplit(r["url"]).path.startswith(path.rstrip("/") + "/")
            )
        if re.fullmatch(r"/v\d+/[^/]+\.html", path):
            return ""
        return None

    def _jmlr_catalog(self, path, records):
        if path == "/papers/":
            return "".join(
                _link("/papers/" + r["identifiers"]["jmlr"].split("/")[0] + "/", r["year"])
                for r in records
            )
        if re.fullmatch(r"/papers/(?:v|volume)\d+/?", path):
            return "".join(
                _link(r["url"], r["title"])
                for r in records
                if urlsplit(r["url"]).path.startswith(path.rstrip("/") + "/")
            )
        if re.fullmatch(r"/papers/(?:v|volume)\d+/[^/]+\.html", path):
            return ""
        return None

    def _acl_catalog(self, path, records):
        volumes = {r["identifiers"]["acl"].rsplit(".", 1)[0] for r in records}
        events = {v.split(".")[1].split("-")[0] + "-" + v.split(".")[0] for v in volumes}
        if path == "/events/":
            return "".join(_link(f"/events/{e}/", e) for e in sorted(events))
        if match := re.fullmatch(r"/events/([a-z]+)-(\d{4})/?", path):
            return "".join(
                _link(f"/volumes/{v}/", v)
                for v in sorted(volumes)
                if v.startswith(match[2] + "." + match[1])
            )
        if path.startswith("/volumes/"):
            volume = path.removeprefix("/volumes/").strip("/")
            return "".join(
                _link(r["url"], r["title"])
                for r in records
                if r["identifiers"]["acl"].startswith(volume + ".")
            )
        if re.fullmatch(r"/\d{4}\.[^/]+/?", path):
            return ""
        return None

    def _neurips_catalog(self, path, records):
        if path == "/":
            return "".join(_link(f"/paper_files/paper/{r['year']}/", r["year"]) for r in records)
        if match := re.fullmatch(r"/(?:paper_files/paper|paper)/(\d{4})/?", path):
            return "".join(
                _link(r["url"], r["title"]) for r in records if str(r["year"]) == match[1]
            )
        if re.fullmatch(r"/(?:paper_files/paper|paper)/\d{4}/hash/[^/]+\.html", path):
            return ""
        return None
