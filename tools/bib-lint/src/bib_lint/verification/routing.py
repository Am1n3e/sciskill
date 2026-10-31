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


@dataclass(frozen=True)
class LookupStep:
    provider: str
    strategy: str
    value: str = ""
    field: str = ""

    def query(self, original):
        if self.strategy == "url":
            return LookupQuery.from_entry(
                {"key": original.citation_key, "fields": {"url": self.value}}
            )
        if self.strategy == "identifier":
            return LookupQuery.from_entry(
                {"key": original.citation_key, "fields": {self.field: self.value}}
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
        return LookupStep(name, "url", url, field)
    return None


def plan_lookups(entry, providers):
    steps, seen = [], set()
    direct = _url_step(entry, providers)
    if direct:
        steps.append(direct)
        field, value = url_locators(direct.value)[0]
        seen.add((field, locator(field, value)))
    for field, alias, raw in supplied_locators(entry.get("fields", {})):
        name = PROVIDERS.get(field, field)
        value = locator(field, raw)
        if alias == "url" or name not in providers or not value or (field, value) in seen:
            continue
        seen.add((field, value))
        steps.append(LookupStep(name, "identifier", value, field))
    steps.extend(LookupStep(name, "search") for name in providers)
    return steps


def resolved(result):
    record = result.get("found_ref")
    return bool(
        result.get("lookup_complete", True)
        and record
        and all(record.get(field) for field in ("title", "authors", "year"))
    )
