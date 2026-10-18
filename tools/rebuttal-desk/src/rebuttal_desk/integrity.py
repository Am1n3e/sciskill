"""Stable checksum of the ordered original review sections."""

import hashlib
import json


def content_checksum(sections):
    original = [
        {"heading": section["heading"], "content": section["content"]}
        for section in sections
    ]
    canonical = json.dumps(original, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
