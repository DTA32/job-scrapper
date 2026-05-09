from __future__ import annotations

from bs4 import BeautifulSoup

from ..types import Job
from .base import Scraper


class IndeedScraper(Scraper):
    name = "indeed"

    def parse(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        cards = (
            soup.select("div.job_seen_beacon")
            or soup.select("td.resultContent")
            or soup.select("div[data-testid='slider_item']")
            or soup.select("li div.cardOutline")
        )
        results: list[Job] = []
        seen: set[str] = set()
        for card in cards:
            title_el = (
                card.select_one("h2.jobTitle span[title]")
                or card.select_one("h2.jobTitle a span")
                or card.select_one("h2.jobTitle")
                or card.select_one("[data-testid='jobTitle']")
            )
            company_el = (
                card.select_one("[data-testid='company-name']")
                or card.select_one("span.companyName")
                or card.select_one("[data-testid='inlineHeader-companyName']")
            )
            loc_el = (
                card.select_one("[data-testid='text-location']")
                or card.select_one("div.companyLocation")
                or card.select_one("[data-testid='job-location']")
            )
            link_el = (
                card.select_one("a.jcs-JobTitle")
                or card.select_one("h2.jobTitle a")
                or card.select_one("a[data-jk]")
            )

            title = title_el.get_text(" ", strip=True) if title_el else None
            if title_el and not title and title_el.has_attr("title"):
                title_attr = title_el.get("title")
                if isinstance(title_attr, str):
                    title = title_attr
                elif isinstance(title_attr, list) and title_attr:
                    title = str(title_attr[0])
            company = company_el.get_text(" ", strip=True) if company_el else None
            location = loc_el.get_text(" ", strip=True) if loc_el else None

            url: str | None = None
            if link_el:
                href_value = link_el.get("href")
                jk_value = link_el.get("data-jk")
                if jk_value:
                    url = f"https://id.indeed.com/viewjob?jk={jk_value}"
                elif href_value:
                    href = str(href_value)
                    url = (
                        f"https://id.indeed.com{href}"
                        if href.startswith("/")
                        else href
                    )

            key = url or f"{title}|{company}"
            if not title or not company or key in seen:
                continue
            seen.add(key)

            results.append(
                Job(
                    site=self.name,
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                )
            )
            if len(results) >= self.limit:
                break
        return results
