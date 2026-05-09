from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import Job


class Scraper(ABC):
    name: str
    url: str

    @abstractmethod
    def parse(self, html: str) -> list[Job]: ...
