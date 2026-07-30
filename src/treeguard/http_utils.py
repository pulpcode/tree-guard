"""Shared HTTP client hardening for explicit side-effect boundaries."""

from __future__ import annotations

import ipaddress
import re
import urllib.request
from typing import Any


_HOSTNAME = re.compile(
    r"^(?=.{1,253}\.?$)"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Fail closed so credentials are never forwarded to a redirect target."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


def build_isolated_opener() -> urllib.request.OpenerDirector:
    """Build an opener that ignores ambient proxies and rejects redirects."""

    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirectHandler(),
    )


def is_protected_environment_host(hostname: str) -> bool:
    """Accept private IPs and explicit internal-only DNS naming forms."""

    normalized = hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return (
            _HOSTNAME.fullmatch(hostname) is not None
            and (
                normalized == "localhost"
                or "." not in normalized
                or normalized.endswith((".internal", ".local", ".lan"))
            )
        )
    return address.is_private or address.is_loopback


__all__ = [
    "NoRedirectHandler",
    "build_isolated_opener",
    "is_protected_environment_host",
]
