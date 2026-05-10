from __future__ import annotations

import sys

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from .base import FetchAttempt, detect_challenge

CHROME_IMPERSONATE = "chrome131"


class CurlCffiFetcher:
    name = "curl_cffi"

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"[curl_cffi] not installed: {exc}", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code="not_installed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        try:
            response = cffi_requests.get(
                url,
                impersonate=CHROME_IMPERSONATE,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": ACCEPT_LANGUAGE,
                },
                timeout=30,
            )
        except Exception as exc:
            print(f"[curl_cffi] error on {url}: {exc}", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            print(f"[curl_cffi] {url} status={status}", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            print(f"[curl_cffi] {url} blocked by challenge page", file=sys.stderr)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, FetchAttempt(fetcher=self.name, code="ok")
