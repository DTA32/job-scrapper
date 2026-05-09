from __future__ import annotations

import sys
import time

from ..config import USER_AGENT
from .base import FetchAttempt, detect_challenge


class PlaywrightFetcher:
    name = "playwright"

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            print(f"[playwright] not installed: {exc}", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code="not_installed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        stealth_v2 = None
        stealth_sync = None
        try:
            from playwright_stealth import Stealth as stealth_v2  # type: ignore
        except Exception:
            try:
                from playwright_stealth import stealth_sync  # type: ignore
            except Exception:
                stealth_sync = None

        try:
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
                    user_agent=USER_AGENT,
                    locale="id-ID",
                    viewport={"width": 1366, "height": 768},
                )
                page = context.new_page()
                if stealth_v2 is not None:
                    stealth_v2().apply_stealth_sync(page)
                elif stealth_sync is not None:
                    stealth_sync(page)

                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
                time.sleep(2)
                html = page.content()
                context.close()
                browser.close()
        except Exception as exc:
            print(f"[playwright] error on {url}: {exc}", file=sys.stderr)
            msg = str(exc)
            lowered = msg.lower()
            if "asyncio" in lowered and "loop" in lowered:
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="runtime_error",
                    detail="asyncio sync-API conflict",
                )
            if "timeout" in lowered:
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="timeout",
                    detail=msg[:200],
                )
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {msg[:200]}",
            )

        challenge = detect_challenge(html)
        if challenge:
            print(f"[playwright] {url} blocked by challenge page", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return html, FetchAttempt(fetcher=self.name, code="ok")
