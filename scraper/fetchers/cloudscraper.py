from __future__ import annotations

import sys

import cloudscraper

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from .base import looks_like_challenge


class CloudscraperFetcher:
    name = "cloudscraper"

    def fetch(self, url: str) -> str | None:
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "linux", "mobile": False}
            )
            scraper.headers.update(
                {"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE}
            )
            response = scraper.get(url, timeout=30)
        except Exception as exc:
            print(f"[cloudscraper] error on {url}: {exc}", file=sys.stderr)
            return None

        if response.status_code != 200:
            print(
                f"[cloudscraper] {url} status={response.status_code}",
                file=sys.stderr,
            )
            return None

        text = response.text
        if looks_like_challenge(text):
            print(f"[cloudscraper] {url} blocked by challenge page", file=sys.stderr)
            return None
        return text
