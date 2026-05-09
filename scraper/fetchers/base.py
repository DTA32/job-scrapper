from __future__ import annotations

import re
import sys
from typing import Protocol, runtime_checkable

from ..config import CHALLENGE_MARKERS

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_CHALLENGE_TITLES = ("just a moment", "attention required", "access denied")


def looks_like_challenge(html: str) -> bool:
    match = _TITLE_RE.search(html)
    if match:
        title = match.group(1).strip().lower()
        if any(t in title for t in _CHALLENGE_TITLES):
            return True
    if len(html) < 4096:
        return any(m in html for m in CHALLENGE_MARKERS)
    return False


@runtime_checkable
class Fetcher(Protocol):
    name: str

    def fetch(self, url: str) -> str | None: ...


class FetchChain:
    def __init__(self, fetchers: list[Fetcher]) -> None:
        self._fetchers = fetchers

    def fetch(self, url: str) -> str | None:
        for fetcher in self._fetchers:
            print(f"[fetch] trying {fetcher.name} for {url}", file=sys.stderr)
            html = fetcher.fetch(url)
            if html and not looks_like_challenge(html):
                return html
            print(
                f"[fetch] {fetcher.name} insufficient, falling through",
                file=sys.stderr,
            )
        return None
