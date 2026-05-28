from __future__ import annotations

from .base import (
    FetchAttempt,
    FetchChain,
    Fetcher,
    FetchResult,
    detect_challenge,
    looks_like_challenge,
)
from .cloudscraper import CloudscraperFetcher
from .curl_cffi import CurlCffiFetcher
from .playwright import PlaywrightFetcher

__all__ = [
    "FetchChain",
    "FetchResult",
    "FetchAttempt",
    "Fetcher",
    "CloudscraperFetcher",
    "CurlCffiFetcher",
    "PlaywrightFetcher",
    "detect_challenge",
    "looks_like_challenge",
]
