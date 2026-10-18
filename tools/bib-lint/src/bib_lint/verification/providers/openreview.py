"""Public OpenReview paper notes with explicit, configured publication qualification."""

import re
from urllib.parse import parse_qs, urlsplit

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.matching import doi, name_parts, normalize
from bib_lint.verification.providers.common import (
    LookupBuilder,
    direct_matches,
    shortlisted,
    source_identifier,
    supported_url,
    years,
)
from bib_lint.verification.providers.protocol import Applicability, Candidate, ProviderDescriptor

V2 = "https://api2.openreview.net"
V1 = "https://api.openreview.net"


def content(note):
    values = note.get("content", {})
    if not isinstance(values, dict):
        raise LookupFailure("invalid_response", "OpenReview content must be an object")
    return {
        k: v.get("value") if isinstance(v, dict) and "value" in v else v for k, v in values.items()
    }


class OpenReviewProvider:
    descriptor = ProviderDescriptor(
        "openreview",
        "OpenReview",
        "1",
        "review_platform",
        ("openreview.net", "api2.openreview.net", "api.openreview.net"),
        discovery_config=(("venues", "ICLR.cc,ICML.cc,NeurIPS.cc,TMLR"),),
    )

    def _discover_venue(self, query, context, venueid):
        offset = 0
        while True:
            notes, count = self._notes(
                context,
                V2,
                "/notes",
                {
                    "content.venueid": venueid,
                    "details": "directReplies,original",
                    "limit": 20,
                    "offset": offset,
                },
            )
            for candidate in self._records(notes):
                if shortlisted(query, candidate.title or ""):
                    yield candidate
            offset += len(notes)
            if (count is not None and offset >= count) or (count is None and len(notes) < 20):
                break
            if not notes:
                raise LookupFailure(
                    "incomplete_search", "OpenReview venue pagination stopped early"
                )

    def _discover_title(self, query, context):
        offset = 0
        while True:
            try:
                notes, count = self._notes(
                    context,
                    V2,
                    "/notes/search",
                    {
                        "term": query.title,
                        "type": "terms",
                        "content": "title",
                        "limit": 20,
                        "offset": offset,
                    },
                )
            except LookupFailure as exc:
                if exc.code not in {"not_found", "access_denied"}:
                    raise
                # Older/public venue searches use API v1's title search route.
                notes, count = self._notes(
                    context,
                    V1,
                    "/notes/search",
                    {"term": query.title, "limit": 20, "offset": offset},
                )
            yield from self._records(notes)
            offset += len(notes)
            if (count is not None and offset >= count) or (count is None and len(notes) < 20):
                break
            if not notes:
                raise LookupFailure("incomplete_search", "OpenReview pagination stopped early")

    def _candidate(self, note):
        values = content(note)
        original = note.get("details", {}).get("original")
        if isinstance(original, dict):
            values = {**content(original), **values}
            if content(original).get("authors"):
                values["authors"] = content(original)["authors"]
        identifier = note.get("id")
        if not identifier or not values.get("title"):
            raise LookupFailure("invalid_response", "OpenReview paper needs note ID and title")
        status, venue, year, proof = self._qualification(note, values)
        authors = values.get("authors") or []
        if not isinstance(authors, list) or any(not isinstance(a, str) for a in authors):
            raise LookupFailure("invalid_response", "OpenReview authors must be a public list")
        authors = [a for a in authors if a.casefold() not in {"anonymous", "anonymous authors"}]
        ids = {"openreview": identifier}
        if values.get("doi"):
            ids["doi"] = doi(values["doi"])
        provenance = {
            "source": f"https://openreview.net/forum?id={identifier}",
            "publication_status": proof,
            "venueid": values.get("venueid") or "",
        }
        for key in ("cdate", "mdate", "pdate", "odate", "version"):
            if note.get(key) is not None:
                provenance[key] = str(note[key])
        return Candidate.from_record(
            {
                "title": values["title"],
                "authors": [name_parts(a) for a in authors],
                "year": year,
                "venue": venue,
                "identifiers": ids,
                "url": f"https://openreview.net/forum?id={identifier}",
                "record_type": "publication" if status == "accepted" else "unknown",
                "publication_status": status,
                "version": str(note.get("version")) if note.get("version") else None,
            },
            provenance=provenance,
        )

    def _public_decision(self, note, match, base, status, proof):
        for reply in note.get("details", {}).get("directReplies", []):
            invitations = reply.get("invitations") or [reply.get("invitation", "")]
            decision = content(reply).get("decision", "")
            if reply.get("forum") != note.get("forum", note.get("id")):
                continue
            if not match or not any(
                re.fullmatch(
                    re.escape(f"{base}/{match[2]}/Conference") + r"(?:/Paper\d+)?/-/Decision", i
                )
                for i in invitations
            ):
                continue
            if isinstance(decision, str) and re.fullmatch(r"Accept(?: \([^()]+\))?", decision):
                status, proof = "accepted", f"public decision note: {reply.get('id', '')}"
            elif decision == "Reject":
                status, proof = "rejected", f"public decision note: {reply.get('id', '')}"
        return status, proof

    def identifier(self, query):
        supported_url(query, self.descriptor.allowed_hosts)
        parsed = urlsplit(query.input_url)
        if parsed.hostname in self.descriptor.allowed_hosts:
            values = parse_qs(parsed.query).get("id", [])
            if values:
                return values[0]
        return source_identifier(query, "openreview", "openreview_id", "forum")

    def applicability(self, query):
        if self.identifier(query) or query.title:
            return Applicability(strategies=("note_id", "title"))
        return Applicability("inapplicable", "No OpenReview identifier or searchable title")

    def _qualification(self, note, values):
        venueid = values.get("venueid") or ""
        venue = values.get("venue") or None
        series = dict(self.descriptor.discovery_config)["venues"].split(",")
        match = re.fullmatch(r"([^/]+)/(\d{4})/Conference(?:/(.*))?", venueid)
        base = (
            match[1]
            if match
            else "TMLR"
            if venueid == "TMLR" or venueid.startswith("TMLR/")
            else None
        )
        qualified = base in series
        suffix = match[3] if match else venueid.removeprefix("TMLR").strip("/")
        status, proof = "unknown", "No explicit publication qualification"
        if match or base == "TMLR":
            if not suffix and qualified:
                status, proof = "accepted", f"accepted venueid: {venueid}"
            elif suffix in {"Rejected_Submission", "Desk_Rejected_Submission"}:
                status, proof = "rejected", f"venueid: {venueid}"
            elif suffix == "Withdrawn_Submission":
                status, proof = "withdrawn", f"venueid: {venueid}"
            elif suffix in {"Submission", "Submitted"}:
                status, proof = "submitted", f"venueid: {venueid}"
        if qualified and status in {"unknown", "submitted"}:
            status, proof = self._public_decision(note, match, base, status, proof)
        year = values.get("year")
        if not year and match and status == "accepted":
            year = match[2]
        return status, venue if status == "accepted" else None, year, proof

    def _records(self, notes):
        for note in notes:
            if not isinstance(note, dict):
                raise LookupFailure("invalid_response", "OpenReview notes must be objects")
            if note.get("replyto") or (note.get("forum") and note.get("forum") != note.get("id")):
                continue
            invitations = note.get("invitations") or [note.get("invitation", "")]
            if any(
                re.search(r"/-/(?:Review|Comment|Decision|Meta_Review|Rebuttal)$", i)
                for i in invitations
            ):
                continue
            yield self._candidate(note)

    def _notes(self, context, base, path, params):
        data = context.json(base + path, params=params, page=True)
        if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
            raise LookupFailure("invalid_response", "Expected OpenReview notes list")
        count = data.get("count")
        return data["notes"], int(count) if count is not None else None

    def lookup(self, query, context):
        builder = LookupBuilder(context)
        identifier = self.identifier(query)
        if identifier:
            for base in (V2, V1):
                builder.run(
                    "note_id",
                    base + "/notes",
                    identifier,
                    lambda base=base: self._records(
                        self._notes(
                            context,
                            base,
                            "/notes",
                            {"id": identifier, "details": "directReplies,original"},
                        )[0]
                    ),
                )
                if not builder.complete or direct_matches(query, builder.candidates):
                    return builder.result()
        if query.title:
            builder.run(
                "title",
                V2 + "/notes/search",
                query.title,
                lambda: self._discover_title(query, context),
            )
            venue = normalize(query.venue)
            series = next(
                (
                    s
                    for s in dict(self.descriptor.discovery_config)["venues"].split(",")
                    if re.search(r"\b" + re.escape(normalize(s.split(".")[0])) + r"\b", venue)
                ),
                None,
            )
            if (
                builder.complete
                and series
                and not any(c.record_type == "publication" for c in builder.candidates)
            ):
                for year in years(query)[:1]:
                    venueid = "TMLR" if series == "TMLR" else f"{series}/{year}/Conference"

                    builder.run(
                        "venue",
                        venueid,
                        query.title,
                        lambda venueid=venueid: self._discover_venue(query, context, venueid),
                    )
        return builder.result()
