"""NeurIPS/NIPS proceedings record and year-catalog discovery."""

import re
from urllib.parse import urlsplit

from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.common import (
    catalog_links,
    shortlisted,
    source_identifier,
    years,
)
from bib_lint.verification.providers.protocol import ProviderDescriptor

ROOT = "https://proceedings.neurips.cc/"


class NeuripsProvider(ArchiveProvider):
    descriptor = ProviderDescriptor(
        "neurips",
        "NeurIPS",
        "1",
        "publication_archive",
        ("proceedings.neurips.cc", "papers.nips.cc"),
    )

    def direct_url(self, query):
        url = super().direct_url(query)
        identifier = source_identifier(query, "neurips", "neurips_id")
        if (
            not url
            and identifier
            and re.fullmatch(r"(?:paper_files/paper|paper)/\d{4}/(?:hash/)?[\w.-]+", identifier)
        ):
            url = ROOT + identifier
        return url

    def catalogs(self, query, context):
        links = list(
            catalog_links(
                context.get(ROOT, page=True),
                ROOT,
                lambda u: bool(
                    re.fullmatch(r"/(?:paper_files/paper|paper)/\d{4}/?", urlsplit(u).path)
                ),
            )
        )
        for year in years(query):
            for url, _, _ in links:
                if urlsplit(url).path.rstrip("/").endswith("/" + str(year)):
                    yield url

    def paper_links(self, text, url, query):
        for target, title, _ in catalog_links(
            text,
            url,
            lambda u: bool(
                re.fullmatch(
                    r"/(?:paper_files/paper|paper)/\d{4}/hash/[^/]+-Abstract[^/]*\.html",
                    urlsplit(u).path,
                )
            ),
        ):
            if shortlisted(query, title):
                yield target
