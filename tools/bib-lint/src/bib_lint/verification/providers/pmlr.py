"""PMLR paper records and official volume-catalog discovery."""

import re
from urllib.parse import urlsplit

from bib_lint.verification.matching import normalize
from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.common import (
    catalog_links,
    shortlisted,
    source_identifier,
    years,
)
from bib_lint.verification.providers.protocol import ProviderDescriptor

ROOT = "https://proceedings.mlr.press/"
VENUES = {
    "icml": ("icml", "international conference on machine learning"),
    "aistats": ("aistats", "artificial intelligence and statistics"),
    "colt": ("colt", "conference on learning theory"),
    "corl": ("corl", "conference on robot learning"),
    "uai": ("uai", "uncertainty in artificial intelligence"),
    "alt": ("alt", "algorithmic learning theory"),
}


class PmlrProvider(ArchiveProvider):
    descriptor = ProviderDescriptor(
        "pmlr", "PMLR", "1", "publication_archive", ("proceedings.mlr.press",)
    )

    def direct_url(self, query):
        url = super().direct_url(query)
        identifier = source_identifier(query, "pmlr", "pmlr_id")
        if not url and identifier and re.fullmatch(r"v\d+/[\w.-]+(?:\.html)?", identifier):
            url = ROOT + identifier.removesuffix(".html") + ".html"
        return url

    def catalogs(self, query, context):
        if self.volume_catalog(query):
            yield self.volume_catalog(query)
            return
        text = context.get(ROOT, page=True)
        venue = normalize(query.venue)
        series = next(
            (
                key
                for key, aliases in VENUES.items()
                if any(normalize(alias) in venue for alias in aliases)
            ),
            None,
        )
        links = list(
            catalog_links(text, ROOT, lambda u: bool(re.fullmatch(r"/v\d+/?", urlsplit(u).path)))
        )
        for year in years(query):
            for url, _, label in links:
                if str(year) in label and (
                    not series or re.search(r"\b" + series + r"\b", label, re.I)
                ):
                    yield url.rstrip("/") + "/"

    def volume_catalog(self, query):
        volume = dict(query.fields).get("volume", "")
        return ROOT + "v" + volume + "/" if re.fullmatch(r"\d+", volume) else None

    def paper_links(self, text, url, query):
        for target, title, _ in catalog_links(
            text, url, lambda u: bool(re.fullmatch(r"/v\d+/[^/]+\.html", urlsplit(u).path))
        ):
            if shortlisted(query, title):
                yield target
