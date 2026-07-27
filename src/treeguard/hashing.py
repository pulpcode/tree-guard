"""Stable schema hashing that deliberately excludes instance VALUE and audit fields."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


AUDIT_FIELDS = {
    "create_time",
    "creator",
    "last_modifier",
    "last_modify_time",
}


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def without_audit_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: without_audit_fields(item)
            for key, item in value.items()
            if key not in AUDIT_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [without_audit_fields(item) for item in value]
    return value
