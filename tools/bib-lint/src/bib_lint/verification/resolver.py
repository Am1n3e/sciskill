"""DOI resolution yields a destination URL, never authoritative paper metadata."""

from urllib.parse import quote, urljoin, urlsplit

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.input_checks import HOSTS, locator
from bib_lint.verification.providers.protocol import (
    Applicability,
    LookupAttempt,
    LookupResult,
    ProviderDescriptor,
)


class DoiResolver:
    descriptor = ProviderDescriptor(
        "doi", "DOI resolver", "1", "resolver", ("doi.org", "dx.doi.org")
    )

    def applicability(self, query):
        value = dict(query.identifiers).get("doi")
        return Applicability() if value and locator("doi", value) else Applicability("inapplicable")

    def lookup(self, query, context):
        identifier = dict(query.identifiers)["doi"]
        url = "https://doi.org/" + quote(identifier, safe="/")
        for _ in range(context.policy.max_redirects + 1):
            try:
                context.get(url, follow_redirects=False)
                return LookupResult(
                    attempts=(LookupAttempt("doi", url, identifier),),
                    diagnostic="Resolver did not provide a destination URL",
                )
            except LookupFailure as exc:
                if exc.code != "redirect":
                    context.lookup_attempts = (
                        LookupAttempt("doi", url, identifier, False, diagnostic=str(exc)),
                    )
                    raise
                target = urljoin(url, str(exc))
            if urlsplit(target).hostname not in self.descriptor.allowed_hosts:
                return LookupResult(
                    attempts=(LookupAttempt("doi", url, identifier, candidate_urls=(target,)),),
                    redirect_url=target,
                )
            url = target
        raise LookupFailure("redirect_limit", "Too many DOI resolver redirects")


def with_resolver(providers):
    supported = any(
        HOSTS.get(host) not in {None, "doi"}
        for provider in providers.values()
        for host in provider.descriptor.allowed_hosts
    )
    return (
        {**providers, "doi": DoiResolver()} if supported and "doi" not in providers else providers
    )
