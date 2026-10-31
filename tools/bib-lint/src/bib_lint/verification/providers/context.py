"""A bounded source-scoped facade over shared checksum-cache transport."""

import json
from urllib.parse import urljoin, urlsplit

from bib_lint.verification.http import LookupFailure


class RequestContext:
    def __init__(self, client, descriptor, citation_key):
        self._client = client
        self.descriptor = descriptor
        self.policy = descriptor.request_policy
        self.fetches = self.pages = self.attempts = self.candidates = 0
        self.start = len(client.evidence)
        client.method = descriptor.id
        client.citation_key = citation_key

    @property
    def evidence(self):
        return self._client.evidence[self.start :]

    def consume_attempt(self):
        if self.attempts >= self.policy.max_attempts:
            raise LookupFailure("incomplete_search", "HTTP attempt budget exhausted")
        consume = getattr(self._client, "attempt_budget", None)
        if consume:
            consume()
        self.attempts += 1

    def shortlist(self, candidate):
        if self.candidates >= self.policy.max_candidates:
            raise LookupFailure("incomplete_search", "Candidate budget exhausted")
        candidate.validate()
        self.candidates += 1
        return candidate

    def _url(self, url):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise LookupFailure("unsupported_url", "Source URL must use HTTP or HTTPS")
        if parsed.hostname not in self.descriptor.allowed_hosts:
            raise LookupFailure(
                "unsupported_host", "URL or redirect is outside declared source hosts"
            )
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            raise LookupFailure("unsupported_url", "Credentials or nonstandard port in source URL")
        return parsed._replace(scheme="https", fragment="").geturl()

    def get(self, url, *, params=None, page=False, follow_redirects=True):
        url = self._url(url)
        if self.fetches >= self.policy.max_fetches:
            raise LookupFailure("incomplete_search", "Logical fetch budget exhausted")
        if page and self.pages >= self.policy.max_pages:
            raise LookupFailure("incomplete_search", "Catalog/search page budget exhausted")
        self.fetches += 1
        if page:
            self.pages += 1
        for hop in range(self.policy.max_redirects + 1):
            try:
                return self._client.get(
                    url,
                    params=params,
                    allowed_hosts=self.descriptor.allowed_hosts,
                    policy=self.policy,
                    budget=self,
                )
            except LookupFailure as exc:
                if exc.code != "redirect" or not follow_redirects:
                    raise
                if hop == self.policy.max_redirects:
                    raise LookupFailure("redirect_limit", "Too many source redirects") from exc
                url = self._url(urljoin(url, str(exc)))
                params = None
        raise AssertionError("Unreachable redirect state")

    def json(self, url, *, params=None, page=False):
        try:
            return json.loads(self.get(url, params=params, page=page))
        except (TypeError, json.JSONDecodeError) as exc:
            raise LookupFailure("invalid_response", "Source did not return valid JSON") from exc
