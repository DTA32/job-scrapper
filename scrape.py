"""Scrape 2 software engineer jobs from jobstreet ID and glints ID.

Strategy: cloudscraper first (cheap). If blocked or empty, fall back to
playwright-stealth (heavier RAM). Sites run sequentially to keep memory low.
Output: jobstreet.json and glints.json in this directory.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import cloudscraper
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
LIMIT = 2
KEYWORD = "software engineer"

JOBSTREET_URL = "https://id.jobstreet.com/id/software-engineer-jobs"
GLINTS_URL = (
    "https://glints.com/id/opportunities/jobs/explore"
    "?keyword=software%20engineer&country=ID"
)
LINKEDIN_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords=software%20engineer&location=Indonesia&start=0"
)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def fetch_cloudscraper(url: str) -> str | None:
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "linux", "mobile": False}
        )
        scraper.headers.update({"User-Agent": UA, "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"})
        r = scraper.get(url, timeout=30)
        if r.status_code != 200:
            print(f"[cloudscraper] {url} status={r.status_code}", file=sys.stderr)
            return None
        text = r.text
        if _looks_like_challenge(text):
            print(f"[cloudscraper] {url} appears blocked by challenge page", file=sys.stderr)
            return None
        return text
    except Exception as e:
        print(f"[cloudscraper] error on {url}: {e}", file=sys.stderr)
        return None


def _looks_like_challenge(html: str) -> bool:
    markers = (
        "Just a moment",
        "challenge-platform",
        "cf-browser-verification",
        "Attention Required",
    )
    return any(m in html for m in markers)


def fetch_playwright(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright

        try:
            from playwright_stealth import Stealth  # v2 API
            stealth_v2 = True
        except Exception:
            stealth_v2 = False
            try:
                from playwright_stealth import stealth_sync  # v1 API
            except Exception:
                stealth_sync = None  # type: ignore

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                ],
            )
            context = browser.new_context(
                user_agent=UA,
                locale="id-ID",
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()
            if stealth_v2:
                Stealth().apply_stealth_sync(page)  # type: ignore[name-defined]
            elif stealth_sync is not None:  # type: ignore[name-defined]
                stealth_sync(page)  # type: ignore[name-defined]

            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            time.sleep(2)
            html = page.content()
            context.close()
            browser.close()
            return html
    except Exception as e:
        print(f"[playwright] error on {url}: {e}", file=sys.stderr)
        return None


def fetch(url: str) -> str | None:
    html = fetch_cloudscraper(url)
    if html and not _looks_like_challenge(html):
        return html
    print(f"[fetch] cloudscraper insufficient, switching to playwright for {url}", file=sys.stderr)
    return fetch_playwright(url)


def _extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _walk(obj: Any, predicate: Callable[[dict], bool], out: list[dict]) -> None:
    if isinstance(obj, dict):
        if predicate(obj):
            out.append(obj)
        for v in obj.values():
            _walk(v, predicate, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, predicate, out)


def parse_jobstreet(html: str) -> list[dict]:
    results: list[dict] = []

    data = _extract_next_data(html)
    if data:
        candidates: list[dict] = []
        _walk(
            data,
            lambda d: ("jobTitle" in d or "title" in d)
            and ("companyName" in d or "advertiser" in d or "company" in d),
            candidates,
        )
        seen = set()
        for c in candidates:
            title = c.get("jobTitle") or c.get("title")
            company = (
                c.get("companyName")
                or (c.get("advertiser") or {}).get("description") if isinstance(c.get("advertiser"), dict) else None
            ) or (c.get("company") if isinstance(c.get("company"), str) else None)
            if isinstance(c.get("company"), dict):
                company = company or c["company"].get("name")
            location = c.get("locationLabel") or c.get("location")
            if isinstance(location, dict):
                location = location.get("label") or location.get("name")
            if isinstance(location, list) and location:
                first = location[0]
                location = first.get("label") if isinstance(first, dict) else str(first)
            if not title or not company:
                continue
            key = (str(title), str(company))
            if key in seen:
                continue
            seen.add(key)
            url = None
            if c.get("id"):
                url = f"https://id.jobstreet.com/id/job/{c['id']}"
            results.append(
                {
                    "site": "jobstreet",
                    "title": str(title).strip(),
                    "company": str(company).strip(),
                    "location": str(location).strip() if location else None,
                    "url": url,
                }
            )
            if len(results) >= LIMIT:
                return results

    # Fallback: HTML selectors
    if len(results) < LIMIT:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("article[data-card-type='JobCard'], article[data-automation='normalJob']")
        for card in cards:
            title_el = card.select_one("[data-automation='jobTitle']") or card.select_one("a")
            company_el = card.select_one("[data-automation='jobCompany']")
            loc_el = card.select_one("[data-automation='jobLocation']")
            title = title_el.get_text(strip=True) if title_el else None
            company = company_el.get_text(strip=True) if company_el else None
            location = loc_el.get_text(strip=True) if loc_el else None
            href = title_el.get("href") if title_el and title_el.name == "a" else None
            url = f"https://id.jobstreet.com{href}" if href and href.startswith("/") else href
            if title and company:
                results.append(
                    {
                        "site": "jobstreet",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": url,
                    }
                )
                if len(results) >= LIMIT:
                    break

    return results[:LIMIT]


def parse_glints(html: str) -> list[dict]:
    results: list[dict] = []

    data = _extract_next_data(html)
    if data:
        candidates: list[dict] = []
        _walk(
            data,
            lambda d: ("title" in d) and ("company" in d or "companyName" in d),
            candidates,
        )
        seen = set()
        for c in candidates:
            title = c.get("title")
            comp_obj = c.get("company")
            company = None
            if isinstance(comp_obj, dict):
                company = comp_obj.get("name")
            elif isinstance(comp_obj, str):
                company = comp_obj
            company = company or c.get("companyName")
            location = (
                c.get("locationName")
                or c.get("cityName")
                or (c.get("city") or {}).get("name") if isinstance(c.get("city"), dict) else None
            ) or c.get("location")
            if isinstance(location, dict):
                location = location.get("name") or location.get("label")
            if not title or not company:
                continue
            key = (str(title), str(company))
            if key in seen:
                continue
            seen.add(key)
            slug = c.get("slug") or c.get("id")
            url = f"https://glints.com/id/opportunities/jobs/{slug}" if slug else None
            results.append(
                {
                    "site": "glints",
                    "title": str(title).strip(),
                    "company": str(company).strip(),
                    "location": str(location).strip() if location else None,
                    "url": url,
                }
            )
            if len(results) >= LIMIT:
                return results

    # Fallback: HTML selectors
    if len(results) < LIMIT:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("a[href*='/opportunities/jobs/']")
        seen_urls: set[str] = set()
        for a in cards:
            href = a.get("href") or ""
            if href in seen_urls:
                continue
            seen_urls.add(href)
            title = (a.select_one("h2,h3,h4") or a).get_text(" ", strip=True)
            container = a.find_parent()
            company_el = (
                container.find(class_=re.compile(r"CompanyName", re.I)) if container else None
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
                    {
                        "site": "glints",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": url,
                    }
                )
                if len(results) >= LIMIT:
                    break

    return results[:LIMIT]


def parse_linkedin(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []
    cards = soup.select("li") or soup.select("div.base-search-card")
    for card in cards:
        title_el = card.select_one("h3.base-search-card__title") or card.select_one(
            ".base-search-card__title"
        )
        company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one(
            ".base-search-card__subtitle"
        )
        loc_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")

        title = title_el.get_text(" ", strip=True) if title_el else None
        company = company_el.get_text(" ", strip=True) if company_el else None
        location = loc_el.get_text(" ", strip=True) if loc_el else None
        href = link_el.get("href") if link_el else None
        url = href.split("?")[0] if href else None

        if title and company:
            results.append(
                {
                    "site": "linkedin",
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                }
            )
            if len(results) >= LIMIT:
                break

    return results[:LIMIT]


def scrape_site(name: str, url: str, parser: Callable[[str], list[dict]], out_path: Path) -> None:
    print(f"[{name}] fetching {url}")
    html = fetch(url)
    if not html:
        print(f"[{name}] FAILED: no html", file=sys.stderr)
        out_path.write_text(json.dumps({"error": "fetch failed", "url": url}, indent=2))
        return
    debug_path = out_path.with_suffix(".debug.html")
    debug_path.write_text(html)
    print(f"[{name}] saved raw html → {debug_path.name} ({len(html)} bytes)")

    jobs = parser(html)
    print(f"[{name}] parsed {len(jobs)} job(s)")
    out_path.write_text(json.dumps({"keyword": KEYWORD, "count": len(jobs), "jobs": jobs}, indent=2))
    print(f"[{name}] wrote {out_path.name}")


def main() -> int:
    targets = sys.argv[1:] or ["jobstreet", "glints", "linkedin"]
    if "jobstreet" in targets:
        scrape_site("jobstreet", JOBSTREET_URL, parse_jobstreet, ROOT / "jobstreet.json")
    if "glints" in targets:
        scrape_site("glints", GLINTS_URL, parse_glints, ROOT / "glints.json")
    if "linkedin" in targets:
        scrape_site("linkedin", LINKEDIN_URL, parse_linkedin, ROOT / "linkedin.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
