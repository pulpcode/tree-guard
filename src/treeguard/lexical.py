"""Shared deterministic term extraction for dependency-free retrieval baselines."""

from __future__ import annotations

import re


_ASCII_WORD = re.compile(r"[a-z0-9]+")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


def text_terms(value: str) -> set[str]:
    """Preserve the v1 ASCII/CJK character and bigram tokenization contract."""

    if not isinstance(value, str):
        raise TypeError("text_terms requires a string")
    normalized = value.lower()
    terms = set(_ASCII_WORD.findall(normalized))
    for run in _CJK_RUN.findall(normalized):
        terms.update(run)
        terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return {term for term in terms if term}


__all__ = ["text_terms"]
