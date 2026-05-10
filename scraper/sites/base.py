from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..types import Job

if TYPE_CHECKING:
    from ..fetchers import FetchChain, FetchResult


class Scraper(ABC):
    name: str

    def __init__(self, url: str, limit: int) -> None:
        self.url = url
        self.limit = limit

    @abstractmethod
    def parse(self, html: str) -> list[Job]: ...

    def parse_detail(self, html: str) -> str | None:
        return None

    def detail_fetch(self, url: str, fetcher: "FetchChain") -> "FetchResult":
        return fetcher.fetch(url)
