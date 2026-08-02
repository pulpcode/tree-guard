"""Shared deterministic checks for locally validated model text."""

from __future__ import annotations

import re
from collections.abc import Iterable


_FABRICATED_INTERNAL_ID = re.compile(
    r"(?i)(?:"
    r"\b(?:node|tree)[-_:/]\d[A-Za-z0-9._:@/-]*\b"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
    r"|\b[0-9a-f]{24}\b"
    r"|\b[0-9a-f]{64}\b"
    r")"
)


def contains_internal_identifier(
    text_values: Iterable[str],
    node_ids: Iterable[str],
) -> bool:
    """Return whether model text contains a known or identifier-like node ID."""

    texts = tuple(text_values)
    if any(_FABRICATED_INTERNAL_ID.search(text) for text in texts):
        return True
    for node_id in node_ids:
        if not node_id:
            continue
        if any(
            (node_id in text if len(node_id) >= 4 else node_id == text)
            for text in texts
        ):
            return True
    return False


__all__ = ["contains_internal_identifier"]
