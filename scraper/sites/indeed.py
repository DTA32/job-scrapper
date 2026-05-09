from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..types import Job, empty_job
from .base import Scraper

_RELATIVE_TIME_RE = re.compile(r'"formattedRelativeTime":"([^"]+)"')
_PUB_DATE_RE = re.compile(r'"pubDate":(\d+)')
_JOBKEY_RE = re.compile(r'"jobkey":"([0-9a-f]+)"')


def _extract_date_map(html: str) -> dict[str, dict[str, str]]:
    rels = _RELATIVE_TIME_RE.findall(html)
    pubs = _PUB_DATE_RE.findall(html)
    jks = _JOBKEY_RE.findall(html)

    mapping: dict[str, dict[str, str]] = {}
    for index, jobkey in enumerate(jks):
        if jobkey in mapping:
            continue
        info: dict[str, str] = {}
        if index < len(rels):
            info["posted_date"] = rels[index]
        if index < len(pubs):
            try:
                seconds = int(pubs[index]) / 1000
                info["posted_at"] = datetime.fromtimestamp(
                    seconds, tz=timezone.utc
                ).isoformat()
            except (ValueError, OSError):
                pass
        if info:
            mapping[jobkey] = info
    return mapping


class IndeedScraper(Scraper):
    name = "indeed"

    def parse(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        date_map = _extract_date_map(html)
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
            salary_el = (
                card.select_one("[data-testid='attribute_snippet_testid']")
                or card.select_one(".salary-snippet-container")
                or card.select_one(".metadata.salary-snippet-container")
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
            salary = salary_el.get_text(" ", strip=True) if salary_el else None

            url: str | None = None
            jk: str | None = None
            if link_el:
                href_value = link_el.get("href")
                jk_value = link_el.get("data-jk")
                if jk_value:
                    jk = str(jk_value)
                    url = f"https://id.indeed.com/viewjob?jk={jk}"
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

            job = empty_job(self.name, title, company)
            job["location"] = location
            job["url"] = url
            job["job_id"] = jk
            job["salary"] = salary

            date_info = date_map.get(jk) if jk else None
            if date_info:
                job["posted_date"] = date_info.get("posted_date")
                job["posted_at"] = date_info.get("posted_at")

            results.append(job)
            if len(results) >= self.limit:
                break
        return results
