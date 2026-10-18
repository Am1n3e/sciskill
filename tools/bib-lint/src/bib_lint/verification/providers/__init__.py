"""Explicit built-in registry. Extensions implement the same retrieval protocol."""

from bib_lint.verification.providers.acl_anthology import AclAnthologyProvider
from bib_lint.verification.providers.arxiv import ArxivProvider
from bib_lint.verification.providers.jmlr import JmlrProvider
from bib_lint.verification.providers.neurips import NeuripsProvider
from bib_lint.verification.providers.openreview import OpenReviewProvider
from bib_lint.verification.providers.pmlr import PmlrProvider
from bib_lint.verification.providers.registry import validate_registry

METHODS = validate_registry(
    [
        ArxivProvider(),
        PmlrProvider(),
        JmlrProvider(),
        AclAnthologyProvider(),
        NeuripsProvider(),
        OpenReviewProvider(),
    ]
)
