"""JMLR independent volume and paper metadata retrieval."""

import re
from urllib.parse import urljoin, urlsplit

from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.common import (
    catalog_links,
    html,
    shortlisted,
    source_identifier,
    years,
)
from bib_lint.verification.providers.protocol import ProviderDescriptor

ROOT = "https://jmlr.org/papers/"


class JmlrProvider(ArchiveProvider):
    descriptor = ProviderDescriptor(
        "jmlr", "JMLR", "2", "publication_archive", ("jmlr.org", "www.jmlr.org")
    )

    def direct_url(self, query):
        url = super().direct_url(query)
        identifier = source_identifier(query, "jmlr", "jmlr_id")
        if not url and identifier and re.fullmatch(r"(?:v|volume)\d+/[\w.-]+", identifier):
            url = ROOT + identifier.removesuffix(".html") + ".html"
        return url

    def catalogs(self, query, context):
        if self.volume_catalog(query):
            yield self.volume_catalog(query)
            return
        links = list(
            catalog_links(
                context.get(ROOT, page=True),
                ROOT,
                lambda u: bool(re.fullmatch(r"/papers/(?:v|volume)\d+/?", urlsplit(u).path)),
            )
        )
        seen = set()
        for year in years(query):
            for url, _, label in links:
                if str(year) in label and url not in seen:
                    seen.add(url)
                    yield url.rstrip("/") + "/"

    def volume_catalog(self, query):
        volume = dict(query.fields).get("volume", "")
        return ROOT + "v" + volume + "/" if re.fullmatch(r"\d+", volume) else None

    def paper_links(self, text, url, query):
        seen = set()
        for anchor in html(text).find_all("a", href=True):
            target = urljoin(url, anchor["href"])
            if target in seen or not re.fullmatch(
                r"/papers/(?:v|volume)\d+/[^/]+\.html", urlsplit(target).path
            ):
                continue
            seen.add(target)
            title = anchor.get_text(" ", strip=True)
            if title.strip("[]").casefold() in {"abs", "abstract"}:
                heading = anchor.find_previous("dt")
                title = heading.get_text(" ", strip=True) if heading else ""
            if shortlisted(query, title):
                yield target
