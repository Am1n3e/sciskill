"""PMLR paper records and official volume-catalog discovery."""

import re
from urllib.parse import urljoin, urlsplit

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.matching import normalize
from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.common import (
    catalog_links,
    html,
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
        "pmlr", "PMLR", "3", "publication_archive", ("proceedings.mlr.press",)
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
        targets = list(
            dict.fromkeys(
                url.rstrip("/") + "/"
                for year in years(query)
                for url, _, label in links
                if str(year) in label
                and (not series or re.search(r"\b" + series + r"\b", label, re.I))
            )
        )
        if not series and len(targets) > context.policy.max_pages - context.pages:
            raise LookupFailure(
                "incomplete_search",
                "PMLR discovery spans too many volumes; "
                "provide a venue, volume, or direct paper URL",
            )
        yield from targets

    def volume_catalog(self, query):
        volume = dict(query.fields).get("volume", "")
        return ROOT + "v" + volume + "/" if re.fullmatch(r"\d+", volume) else None

    def paper_links(self, text, url, query):
        seen = set()
        for anchor in html(text).find_all("a", href=True):
            target = urljoin(url, anchor["href"])
            if target in seen or not re.fullmatch(r"/v\d+/[^/]+\.html", urlsplit(target).path):
                continue
            paper = anchor.find_parent("div", class_="paper")
            heading = paper.find("p", class_="title") if paper else None
            title = (heading or anchor).get_text(" ", strip=True)
            if shortlisted(query, title):
                seen.add(target)
                yield target
