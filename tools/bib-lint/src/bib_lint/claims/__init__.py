"""Claim checks: small, replaceable extractor and validator modules."""

from importlib import import_module

from bib_lint.claims.protocols import Validator


def load_validator(name: str) -> Validator:
    """Import a validator by its exact module name, without a registry."""
    if not name.isidentifier() or name.startswith("_"):
        raise ValueError(f"Invalid validator name: {name!r}")
    module_name = f"bib_lint.claims.validators.{name}"
    try:
        validator = import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        raise ValueError(f"Unknown validator: {name!r}") from error
    if not isinstance(validator, Validator):
        raise ValueError(f"Invalid validator protocol: {name!r}")
    return validator
