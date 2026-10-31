"""Resolve supplied locators before invoking independent source discovery."""

from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from bib_lint.verification.input_checks import (
    ALIASES,
    invalid_url_characters,
    locator,
    supplied_locators,
    url_locators,
)
from bib_lint.verification.providers.protocol import LookupQuery

PROVIDERS = {"acl": "acl_anthology"}


def _metadata_url(url, field, value):
    parsed = urlsplit(url)
    if parsed.path.lower().endswith(".pdf"):
        paths = {
            "pmlr": f"/{value}.html",
            "acl": f"/{value}/",
            "neurips": f"/{value}.html",
        }
        if field in paths:
            return parsed._replace(path=paths[field]).geturl()
    return url


@dataclass(frozen=True)
class LookupStep:
    provider: str
    strategy: str
    value: str = ""
    field: str = ""

    def query(self, original):
        if self.strategy == "url":
            fields = {"url": self.value}
            for field, raw in url_locators(self.value):
                fields[field] = locator(field, raw)
                fields["url"] = _metadata_url(self.value, field, fields[field])
            return LookupQuery.from_entry({"key": original.citation_key, "fields": fields})
        if self.strategy in {"identifier", "resolve"}:
            value = self.value
            if self.field == "neurips" and "-Abstract" in value and not value.endswith(".html"):
                value += ".html"
            return LookupQuery.from_entry(
                {"key": original.citation_key, "fields": {self.field: value}}
            )
        field = "acl" if self.provider == "acl_anthology" else self.provider
        removed = {*ALIASES.get(field, ()), "url", "eprint", "archiveprefix"}
        return replace(
            original,
            input_url="",
            identifiers=tuple((k, v) for k, v in original.identifiers if k != field),
            fields=tuple((k, v) for k, v in original.fields if k not in removed),
        )


def _url_step(entry, providers):
    url = entry.get("fields", {}).get("url", "")
    if invalid_url_characters(url):
        return None
    values = url_locators(url)
    if len(values) != 1:
        return None
    field, raw = values[0]
    name = PROVIDERS.get(field, field)
    provider = providers.get(name)
    value = locator(field, raw)
    if provider and value and urlsplit(url).hostname in provider.descriptor.allowed_hosts:
        if provider.descriptor.evidence_category == "resolver":
            return LookupStep(name, "resolve", value, field)
        return LookupStep(name, "url", url, field)
    return None


def _append(steps, step, providers, redirects):
    steps.append(step)
    if step.strategy == "resolve" and step.value in redirects:
        target = _url_step({"fields": {"url": redirects[step.value]}}, providers)
        if target and target.strategy == "url":
            steps.append(target)


def plan_lookups(entry, providers, redirects=None):
    redirects = redirects or {}
    steps, seen = [], set()
    direct = _url_step(entry, providers)
    if direct:
        _append(steps, direct, providers, redirects)
        field, value = url_locators(entry["fields"]["url"])[0]
        seen.add((field, locator(field, value)))
    for field, alias, raw in supplied_locators(entry.get("fields", {})):
        name = PROVIDERS.get(field, field)
        value = locator(field, raw)
        if alias == "url" or name not in providers or not value or (field, value) in seen:
            continue
        seen.add((field, value))
        strategy = (
            "resolve"
            if providers[name].descriptor.evidence_category == "resolver"
            else "identifier"
        )
        _append(steps, LookupStep(name, strategy, value, field), providers, redirects)
    steps.extend(
        LookupStep(name, "search")
        for name, provider in providers.items()
        if provider.descriptor.evidence_category != "resolver"
    )
    return steps


def resolved(result):
    record = result.get("found_ref")
    return bool(
        result.get("lookup_complete", True)
        and record
        and record.get("title")
        and record.get("authors")
        and (record.get("year") or (result.get("authority") and result.get("differences")))
    )
