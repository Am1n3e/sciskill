"""Shared artifact checksums."""

import hashlib


def digest(value):
    return hashlib.sha256(value).hexdigest()
