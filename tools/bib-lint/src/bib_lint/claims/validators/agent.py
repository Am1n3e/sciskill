"""Support decisions belong to the skill agent; Python preserves that assessment."""

from bib_lint.claims.protocols import Claim, Validation


def validate(claim: Claim, citation_key: str) -> Validation:
    if claim.assessment is None:
        return Validation("unresolved", "Awaiting comparison with the cited paper PDF.")
    return claim.assessment
