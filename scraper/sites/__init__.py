from __future__ import annotations

from .base import Scraper
from .glints import GlintsScraper
from .jobstreet import JobstreetScraper
from .linkedin import LinkedinScraper

SCRAPERS: dict[str, type[Scraper]] = {
    cls.name: cls for cls in (JobstreetScraper, GlintsScraper, LinkedinScraper)
}

__all__ = [
    "Scraper",
    "SCRAPERS",
    "JobstreetScraper",
    "GlintsScraper",
    "LinkedinScraper",
]
