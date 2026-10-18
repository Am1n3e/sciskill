"""ACL Anthology identifiers, event/volume discovery and source BibTeX."""

import re
from urllib.parse import urljoin, urlsplit

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.matching import normalize
from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.common import (
    bibtex_candidate,
    catalog_links,
    citation_candidate,
    html,
    shortlisted,
    source_identifier,
    years,
)
from bib_lint.verification.providers.protocol import ProviderDescriptor

ROOT = "https://aclanthology.org/"
PAPER_ID = r"(?:\d{4}\.[a-z][a-z0-9_-]*-\d+\.\d+|[A-Z]\d{2}-\d{4}|\d{4}\.[a-z][a-z0-9_-]*\.\d+)"
VENUES = {
    "acl": ("acl", "annual meeting of the association for computational linguistics"),
    "emnlp": ("emnlp", "empirical methods in natural language processing"),
    "naacl": ("naacl", "north american chapter"),
    "eacl": ("eacl", "european chapter"),
    "coling": ("coling", "computational linguistics conference"),
    "findings": ("findings",),
}


class AclAnthologyProvider(ArchiveProvider):
    descriptor = ProviderDescriptor(
        "acl_anthology", "ACL Anthology", "2", "publication_archive", ("aclanthology.org",)
    )

    def direct_url(self, query):
        url = super().direct_url(query)
        identifier = source_identifier(query, "acl", "acl_id", "anthology_id", "acl_anthology")
        if not url and identifier and re.fullmatch(PAPER_ID, identifier):
            url = ROOT + identifier + "/"
        return url

    def identifiers(self, url):
        return {"acl": urlsplit(url).path.strip("/").removesuffix(".bib")}

    def fetch_record(self, context, url):
        text = context.get(url)
        candidate = citation_candidate(text, url, self.identifiers(url))
        if candidate:
            yield candidate
            return
        soup = html(text)
        for anchor in soup.find_all("a", href=True):
            if anchor["href"].endswith(".bib"):
                candidate = bibtex_candidate(
                    context.get(urljoin(url, anchor["href"])), url, self.identifiers(url)
                )
                if candidate:
                    yield candidate
                return

    def catalogs(self, query, context):
        if self.volume_catalog(query):
            yield self.volume_catalog(query)
            return
        venue = normalize(query.venue)
        series = next(
            (
                k
                for k, aliases in VENUES.items()
                if any(re.search(r"\b" + re.escape(normalize(a)) + r"\b", venue) for a in aliases)
            ),
            None,
        )
        if series:
            events = [f"{ROOT}events/{series}-{year}/" for year in years(query)]
        else:
            # The event index supplies real locators; never invent a year-only route.
            index = ROOT + "events/"
            links = list(
                catalog_links(
                    context.get(index, page=True),
                    index,
                    lambda u: bool(re.fullmatch(r"/events/[a-z0-9_-]+-\d{4}/?", urlsplit(u).path)),
                )
            )
            events = [
                target
                for year in years(query)
                for target, _, _ in links
                if urlsplit(target).path.rstrip("/").endswith("-" + str(year))
            ]
        events = list(dict.fromkeys(events))
        if not series and len(events) > context.policy.max_pages - context.pages:
            raise LookupFailure(
                "incomplete_search",
                "ACL discovery spans too many events; provide a venue, volume, or direct paper URL",
            )
        for event in events:
            try:
                text = context.get(event, page=True)
            except LookupFailure as exc:
                if exc.code == "not_found":
                    continue
                raise
            for target, _, _ in catalog_links(
                text,
                event,
                lambda u: bool(
                    re.fullmatch(
                        r"/(?:volumes/)?(?:\d{4}\.[a-z0-9_-]+|[A-Z]\d{2}-\d)/?", urlsplit(u).path
                    )
                ),
            ):
                yield target

    def volume_catalog(self, query):
        volume = dict(query.fields).get("volume", "")
        if re.fullmatch(r"(?:\d{4}\.[a-z0-9_-]+|[A-Z]\d{2}-\d)", volume):
            return ROOT + "volumes/" + volume + "/"
        return None

    def paper_links(self, text, url, query):
        for target, title, _ in catalog_links(
            text, url, lambda u: bool(re.fullmatch("/" + PAPER_ID + "/?", urlsplit(u).path))
        ):
            if shortlisted(query, title):
                yield target
