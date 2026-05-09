from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import Job


class Scraper(ABC):
    name: str

    def __init__(self, url: str, limit: int) -> None:
        self.url = url
        self.limit = limit

    @abstractmethod
    def parse(self, html: str) -> list[Job]: ...
