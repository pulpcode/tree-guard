"""Shared HTTP client hardening for explicit side-effect boundaries."""

from __future__ import annotations

import urllib.request
from typing import Any


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


__all__ = ["NoRedirectHandler", "build_isolated_opener"]
