"""Official deterministic validator for testing extraction and artifact workflows."""

from bib_lint.claims.protocols import Claim, Validation


def validate(claim: Claim, citation_key: str) -> Validation:
    return Validation("valid", "Stub mode.")
