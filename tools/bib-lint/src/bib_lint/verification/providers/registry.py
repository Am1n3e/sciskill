"""Explicit trusted registry; no plugin imports or source-specific execution branches."""

from collections.abc import Mapping

from bib_lint.verification.providers.protocol import ProviderDescriptor


def validate_registry(providers):
    if isinstance(providers, Mapping):
        values = list(providers.values())
    else:
        values = list(providers)
    registry = {}
    for provider in values:
        descriptor = getattr(provider, "descriptor", None)
        if not isinstance(descriptor, ProviderDescriptor):
            raise ValueError("Provider must declare a ProviderDescriptor")
        descriptor.validate()
        if descriptor.id in registry:
            raise ValueError(f"Duplicate provider ID: {descriptor.id}")
        if not callable(getattr(provider, "applicability", None)) or not callable(
            getattr(provider, "lookup", None)
        ):
            raise ValueError(f"Provider must implement applicability and lookup: {descriptor.id}")
        registry[descriptor.id] = provider
    if isinstance(providers, Mapping) and list(providers) != list(registry):
        raise ValueError("Registry keys must match ordered provider IDs")
    return registry
