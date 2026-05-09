from __future__ import annotations

import sys
from typing import Protocol, runtime_checkable

from ..config import CHALLENGE_MARKERS


def looks_like_challenge(html: str) -> bool:
    return any(m in html for m in CHALLENGE_MARKERS)


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
