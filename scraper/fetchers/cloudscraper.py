from __future__ import annotations

import sys

import cloudscraper

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from .base import FetchAttempt, detect_challenge


class CloudscraperFetcher:
    name = "cloudscraper"

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
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
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            print(
                f"[cloudscraper] {url} status={status}",
                file=sys.stderr,
            )
            return None, FetchAttempt(
                fetcher=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            print(f"[cloudscraper] {url} blocked by challenge page", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, FetchAttempt(fetcher=self.name, code="ok")
