"""Official arXiv Atom ID and bounded title search."""

import re

from defusedxml import ElementTree

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.matching import arxiv_id, doi, name_parts, plain
from bib_lint.verification.providers.common import (
    LookupBuilder,
    direct_matches,
    source_identifier,
    supported_url,
)
from bib_lint.verification.providers.protocol import (
    Applicability,
    Candidate,
    ProviderDescriptor,
    RequestPolicy,
)

API = "https://export.arxiv.org/api/query"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "x": "http://arxiv.org/schemas/atom",
    "o": "http://a9.com/-/spec/opensearch/1.1/",
}


class ArxivProvider:
    descriptor = ProviderDescriptor(
        "arxiv",
        "arXiv",
        "1",
        "preprint_archive",
        ("export.arxiv.org", "arxiv.org"),
        10,
        RequestPolicy(interval=3.1),
    )

    def identifier(self, query):
        supported_url(query, self.descriptor.allowed_hosts)
        return dict(query.identifiers).get("arxiv") or arxiv_id(
            source_identifier(query, "arxiv", "arxiv_id")
        )

    def applicability(self, query):
        if self.identifier(query) or query.title:
            return Applicability(strategies=("arxiv_id", "title"))
        return Applicability("inapplicable", "No arXiv identifier or searchable title")

    def _page(self, context, params):
        root = ElementTree.fromstring(context.get(API, params=params, page=True))
        if root.tag != "{http://www.w3.org/2005/Atom}feed":
            raise LookupFailure("invalid_response", "Expected arXiv Atom feed")
        entries = root.findall("a:entry", NS)
        total = root.findtext("o:totalResults", namespaces=NS)
        return root, entries, int(total) if total is not None else len(entries)

    def _records(self, entries):
        for entry in entries:
            url = entry.findtext("a:id", namespaces=NS)
            identifier = arxiv_id(url)
            if not identifier:
                raise LookupFailure("invalid_response", "arXiv returned an error record")
            ids = {"arxiv": identifier}
            value = entry.findtext("x:doi", namespaces=NS)
            if value:
                ids["doi"] = doi(value)
            yield Candidate.from_record(
                {
                    "title": entry.findtext("a:title", namespaces=NS),
                    "authors": [
                        name_parts(a.findtext("a:name", namespaces=NS) or "")
                        for a in entry.findall("a:author", NS)
                    ],
                    "year": (entry.findtext("a:published", default="", namespaces=NS))[:4],
                    "venue": "arXiv",
                    "identifiers": ids,
                    "url": f"https://arxiv.org/abs/{identifier}",
                    "version": identifier,
                    "record_type": "preprint",
                    "publication_status": "published",
                },
                provenance={"source": url or "", "year": "published", "metadata": "arxiv_atom"},
            )

    def lookup(self, query, context):
        builder = LookupBuilder(context)
        identifier = self.identifier(query)
        if identifier:
            builder.run(
                "arxiv_id",
                API,
                identifier,
                lambda: self._records(self._page(context, {"id_list": identifier})[1]),
            )
            if not builder.complete or direct_matches(query, builder.candidates):
                return builder.result()
        if query.title:
            title = re.sub(r"[^\w\s-]", " ", plain(query.title))

            def discover():
                start = 0
                while True:
                    _, entries, total = self._page(
                        context,
                        {"search_query": f'ti:"{title}"', "start": start, "max_results": 20},
                    )
                    yield from self._records(entries)
                    start += len(entries)
                    if start >= total:
                        break
                    if not entries:
                        raise LookupFailure("incomplete_search", "arXiv pagination stopped early")

            builder.run("title", API, query.title, discover)
        return builder.result()
