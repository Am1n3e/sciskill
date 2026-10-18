"""Common archive pipeline. Subclasses own URLs, routing and catalog parsing."""

from dataclasses import replace
from urllib.parse import urlsplit

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.providers.common import (
    LookupBuilder,
    citation_candidate,
    direct_matches,
    supported_url,
    years,
)
from bib_lint.verification.providers.protocol import Applicability, LookupAttempt, LookupResult


class ArchiveProvider:
    def _discover_catalogs(self, query, context, builder):
        try:
            for url in self.catalogs(query, context):

                def discover(url=url):
                    text = context.get(url, page=True)
                    for paper in self.paper_links(text, url, query):
                        yield from self.fetch_record(context, paper)

                if not builder.run("catalog", url, query.title, discover):
                    break
        except LookupFailure as exc:
            if exc.code != "incomplete_search":
                raise
            builder.complete = False
            builder.diagnostic = str(exc)
            builder.attempts.append(
                LookupAttempt(
                    "catalog_routing",
                    self.descriptor.display_name,
                    query.title,
                    False,
                    diagnostic=str(exc),
                )
            )

    def direct_url(self, query):
        return supported_url(query, self.descriptor.allowed_hosts)

    def applicability(self, query):
        if self.direct_url(query):
            return Applicability(strategies=("direct", "catalog"))
        if query.title and (years(query) or self.volume_catalog(query)):
            return Applicability(strategies=("catalog",))
        if query.title:
            return Applicability(
                "insufficient_context",
                "Archive discovery needs year or volume context",
                ("catalog",),
            )
        return Applicability("inapplicable", "No supported source identifier, URL or title")

    def fetch_record(self, context, url):
        candidate = citation_candidate(context.get(url), url, self.identifiers(url))
        if candidate:
            yield candidate

    def identifiers(self, url):
        return {self.descriptor.id: urlsplit(url).path.strip("/").removesuffix(".html")}

    def volume_catalog(self, query):
        return None

    def catalogs(self, query, context):
        raise NotImplementedError

    def paper_links(self, text, url, query):
        raise NotImplementedError

    def lookup(self, query, context):
        builder = LookupBuilder(context)
        direct = self.direct_url(query)
        if direct:
            builder.run("direct", direct, direct, lambda: self.fetch_record(context, direct))
            if not builder.complete or direct_matches(query, builder.candidates):
                return builder.result()
        if not query.title:
            return builder.result()
        if not years(query) and not self.volume_catalog(query):
            return LookupResult(
                tuple(builder.candidates),
                tuple(builder.attempts)
                + (
                    LookupAttempt(
                        "catalog",
                        self.descriptor.display_name,
                        query.title,
                        False,
                        diagnostic="Missing year or volume routing context",
                    ),
                ),
                False,
                "Missing year or volume routing context",
            )
        self._discover_catalogs(query, context, builder)
        result = builder.result()
        if not result.attempts:
            result = replace(
                result,
                attempts=(
                    LookupAttempt(
                        "catalog_routing",
                        self.descriptor.display_name,
                        f"{query.venue or ''} {query.year or ''}",
                    ),
                ),
            )
        return result
