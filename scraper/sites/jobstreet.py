from __future__ import annotations

from bs4 import BeautifulSoup

from ..config import LIMIT
from ..types import Job
from ._next_data import extract_next_data, walk_dicts
from .base import Scraper


def _company_from_candidate(candidate: dict) -> str | None:
    if "companyName" in candidate:
        return candidate["companyName"]
    advertiser = candidate.get("advertiser")
    if isinstance(advertiser, dict) and advertiser.get("description"):
        return advertiser["description"]
    company = candidate.get("company")
    if isinstance(company, str):
        return company
    if isinstance(company, dict):
        return company.get("name")
    return None


def _location_from_candidate(candidate: dict) -> str | None:
    location = candidate.get("locationLabel") or candidate.get("location")
    if isinstance(location, dict):
        return location.get("label") or location.get("name")
    if isinstance(location, list) and location:
        first = location[0]
        if isinstance(first, dict):
            return first.get("label")
        return str(first)
    if isinstance(location, str):
        return location
    return None


class JobstreetScraper(Scraper):
    name = "jobstreet"
    url = "https://id.jobstreet.com/id/software-engineer-jobs"

    def parse(self, html: str) -> list[Job]:
        results: list[Job] = []
        results.extend(self._parse_next_data(html))
        if len(results) >= LIMIT:
            return results[:LIMIT]
        results.extend(self._parse_html(html, skip=len(results)))
        return results[:LIMIT]

    def _parse_next_data(self, html: str) -> list[Job]:
        data = extract_next_data(html)
        if not data:
            return []
        candidates: list[dict] = []
        walk_dicts(
            data,
            lambda d: ("jobTitle" in d or "title" in d)
            and ("companyName" in d or "advertiser" in d or "company" in d),
            candidates,
        )
        results: list[Job] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            title = candidate.get("jobTitle") or candidate.get("title")
            company = _company_from_candidate(candidate)
            if not title or not company:
                continue
            key = (str(title), str(company))
            if key in seen:
                continue
            seen.add(key)
            location = _location_from_candidate(candidate)
            job_id = candidate.get("id")
            results.append(
                Job(
                    site=self.name,
                    title=str(title).strip(),
                    company=str(company).strip(),
                    location=str(location).strip() if location else None,
                    url=f"https://id.jobstreet.com/id/job/{job_id}" if job_id else None,
                )
            )
            if len(results) >= LIMIT:
                break
        return results

    def _parse_html(self, html: str, skip: int) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(
            "article[data-card-type='JobCard'], article[data-automation='normalJob']"
        )
        results: list[Job] = []
        for card in cards:
            title_el = card.select_one("[data-automation='jobTitle']") or card.select_one("a")
            company_el = card.select_one("[data-automation='jobCompany']")
            loc_el = card.select_one("[data-automation='jobLocation']")
            title = title_el.get_text(strip=True) if title_el else None
            company = company_el.get_text(strip=True) if company_el else None
            location = loc_el.get_text(strip=True) if loc_el else None
            href_value = title_el.get("href") if title_el and title_el.name == "a" else None
            href = str(href_value) if href_value else None
            url = (
                f"https://id.jobstreet.com{href}"
                if href and href.startswith("/")
                else href
            )
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
                if len(results) + skip >= LIMIT:
                    break
        return results
