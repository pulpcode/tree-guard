"""Strict JSON parsing for security-sensitive contracts."""

from __future__ import annotations

import json
import math
from typing import Any


_MAX_INTEGER_DIGITS = 1_024


class StrictJSONError(ValueError):
    """Input uses a JSON representation rejected by the local profile."""


class DuplicateJSONKeyError(StrictJSONError):
    """A JSON object contains an ambiguous duplicate member name."""


def strict_json_loads(value: str | bytes | bytearray) -> Any:
    return json.loads(
        value,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
        parse_int=_bounded_int,
        parse_float=_finite_float,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError("duplicate JSON object member")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise StrictJSONError("non-finite JSON number is not allowed")


def _bounded_int(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > _MAX_INTEGER_DIGITS:
        raise StrictJSONError("JSON integer exceeds the local digit limit")
    try:
        return int(value)
    except ValueError as exc:
        raise StrictJSONError("JSON integer is invalid") from exc


def _finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise StrictJSONError("JSON number is invalid") from exc
    if not math.isfinite(parsed):
        raise StrictJSONError("non-finite JSON number is not allowed")
    return parsed


__all__ = [
    "DuplicateJSONKeyError",
    "StrictJSONError",
    "strict_json_loads",
]
