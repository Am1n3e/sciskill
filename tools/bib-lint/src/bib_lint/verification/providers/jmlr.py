"""JMLR independent volume and paper metadata retrieval."""

import re
from urllib.parse import unquote, urljoin, urlsplit

from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.common import (
    catalog_links,
    html,
    shortlisted,
    source_identifier,
    supported_url,
    years,
)
from bib_lint.verification.providers.protocol import ProviderDescriptor

ROOT = "https://jmlr.org/papers/"
HOSTS = ("jmlr.org", "www.jmlr.org")


def _official_path(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in HOSTS
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 80, 443}
                or not parsed.path.startswith("/papers/")
            ):
                return None
            return unquote(parsed.path)
    except ValueError:
        return None
    return unquote(value)


def jmlr_identifier(value):
    """Canonical paper identity from a locator or a safe official HTML/PDF URL."""
    if not isinstance(value, str):
        return None
    path = _official_path(value.strip())
    match = re.fullmatch(r"/?(?:papers/)?(?:v|volume)([1-9]\d*)/(.+?)/?", path or "")
    if not match:
        return None
    parts = match[2].split("/")
    if len(parts) == 2 and parts[1].lower().endswith(".pdf") and parts[1][:-4] == parts[0]:
        paper = parts[0]
    elif len(parts) == 1:
        paper = parts[0]
        if paper.lower().endswith(".html"):
            paper = paper[:-5]
        elif paper.lower().endswith(".pdf"):
            paper = paper[:-4]
    else:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", paper):
        return None
    return f"v{match[1]}/{paper}"


class JmlrProvider(ArchiveProvider):
    descriptor = ProviderDescriptor("jmlr", "JMLR", "4", "publication_archive", HOSTS)

    def direct_url(self, query):
        url = supported_url(query, self.descriptor.allowed_hosts, allow_pdf=True)
        if url and urlsplit(url).path.lower().endswith(".pdf"):
            identifier = jmlr_identifier(url)
            url = ROOT + identifier + ".html" if identifier else None
        identifier = source_identifier(query, "jmlr", "jmlr_id")
        if not url and identifier and re.fullmatch(r"(?:v|volume)\d+/[\w.-]+", identifier):
            url = ROOT + identifier.removesuffix(".html") + ".html"
        elif not url and (canonical := jmlr_identifier(identifier)):
            url = ROOT + canonical + ".html"
        return url

    def identifiers(self, url):
        identifier = jmlr_identifier(url)
        return {"jmlr": identifier} if identifier else super().identifiers(url)

    def catalogs(self, query, context):
        volume = self.volume_catalog(query)
        seen = {volume} if volume else set()
        if volume:
            yield volume
        links = list(
            catalog_links(
                context.get(ROOT, page=True),
                ROOT,
                lambda u: bool(re.fullmatch(r"/papers/(?:v|volume)\d+/?", urlsplit(u).path)),
            )
        )
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
