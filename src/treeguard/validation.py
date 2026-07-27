"""Small validation helpers shared by adapters and the CLI."""

from __future__ import annotations

from collections import Counter

from treeguard.models import ValidationIssue


class IssueCollector:
    def __init__(self) -> None:
        self._issues: list[ValidationIssue] = []

    def error(self, code: str, location: str, message: str) -> None:
        self._issues.append(ValidationIssue("ERROR", code, location, message))

    def warning(self, code: str, location: str, message: str) -> None:
        self._issues.append(ValidationIssue("WARNING", code, location, message))

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        return tuple(self._issues)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self._issues)


def duplicate_non_null(values: list[int | None]) -> set[int]:
    counts = Counter(value for value in values if value is not None)
    return {value for value, count in counts.items() if count > 1}
