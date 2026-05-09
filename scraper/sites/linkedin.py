from __future__ import annotations

from bs4 import BeautifulSoup

from ..config import LIMIT
from ..types import Job
from .base import Scraper


class LinkedinScraper(Scraper):
    name = "linkedin"
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=software%20engineer&location=Indonesia&start=0"
    )

    def parse(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("li") or soup.select("div.base-search-card")
        results: list[Job] = []
        for card in cards:
            title_el = card.select_one("h3.base-search-card__title") or card.select_one(
                ".base-search-card__title"
            )
            company_el = card.select_one(
                "h4.base-search-card__subtitle a"
            ) or card.select_one(".base-search-card__subtitle")
            loc_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link") or card.select_one(
                "a[href*='/jobs/view/']"
            )

            title = title_el.get_text(" ", strip=True) if title_el else None
            company = company_el.get_text(" ", strip=True) if company_el else None
            location = loc_el.get_text(" ", strip=True) if loc_el else None
            href_value = link_el.get("href") if link_el else None
            href = str(href_value) if href_value else None
            url = href.split("?", 1)[0] if href else None

            if title and company:
                results.append(
                    Job(
                        site=self.name,
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                    )
                )
                if len(results) >= LIMIT:
                    break
        return results
