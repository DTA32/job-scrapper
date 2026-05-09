from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..types import Job
from ._next_data import extract_next_data, walk_dicts
from .base import Scraper


def _company_from_candidate(candidate: dict) -> str | None:
    company = candidate.get("company")
    if isinstance(company, dict):
        return company.get("name")
    if isinstance(company, str):
        return company
    return candidate.get("companyName")


def _location_from_candidate(candidate: dict) -> str | None:
    if candidate.get("locationName"):
        return candidate["locationName"]
    if candidate.get("cityName"):
        return candidate["cityName"]
    city = candidate.get("city")
    if isinstance(city, dict) and (city.get("name") or city.get("label")):
        return city.get("name") or city.get("label")
    location = candidate.get("location")
    if isinstance(location, dict):
        return location.get("name") or location.get("label")
    if isinstance(location, str):
        return location
    return None


class GlintsScraper(Scraper):
    name = "glints"

    def parse(self, html: str) -> list[Job]:
        results: list[Job] = []
        results.extend(self._parse_next_data(html))
        if len(results) >= self.limit:
            return results[: self.limit]
        results.extend(self._parse_html(html, skip=len(results)))
        return results[: self.limit]

    def _parse_next_data(self, html: str) -> list[Job]:
        data = extract_next_data(html)
        if not data:
            return []
        candidates: list[dict] = []
        walk_dicts(
            data,
            lambda d: ("title" in d) and ("company" in d or "companyName" in d),
            candidates,
        )
        results: list[Job] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            title = candidate.get("title")
            company = _company_from_candidate(candidate)
            if not title or not company:
                continue
            key = (str(title), str(company))
            if key in seen:
                continue
            seen.add(key)
            location = _location_from_candidate(candidate)
            slug = candidate.get("slug") or candidate.get("id")
            results.append(
                Job(
                    site=self.name,
                    title=str(title).strip(),
                    company=str(company).strip(),
                    location=str(location).strip() if location else None,
                    url=f"https://glints.com/id/opportunities/jobs/{slug}" if slug else None,
                )
            )
            if len(results) >= self.limit:
                break
        return results

    def _parse_html(self, html: str, skip: int) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        anchors = soup.select("a[href*='/opportunities/jobs/']")
        seen_urls: set[str] = set()
        results: list[Job] = []
        for anchor in anchors:
            href_value = anchor.get("href") or ""
            href = str(href_value)
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            title_el = anchor.select_one("h2,h3,h4") or anchor
            title = title_el.get_text(" ", strip=True)
            container = anchor.find_parent()
            company_el = (
                container.find(class_=re.compile(r"CompanyName", re.I))
                if container
                else None
            )
            loc_el = (
                container.find(class_=re.compile(r"Location|Place|City", re.I))
                if container
                else None
            )
            company = company_el.get_text(" ", strip=True) if company_el else None
            location = loc_el.get_text(" ", strip=True) if loc_el else None
            url = href if href.startswith("http") else f"https://glints.com{href}"
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
                if len(results) + skip >= self.limit:
                    break
        return results
