# Structured Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered `print()` calls with Python `logging`, write a `logs/status.json` after every `scrape_jobs` MCP call, and expose a `get_scrape_status()` MCP tool so bots can query the last run summary, last error, per-site status, and recent log lines.

**Architecture:** A single `scraper/log.py` module exposes `get_logger()` which lazily sets up one `StreamHandler` (stderr) and one `RotatingFileHandler` (`logs/scraper.log`, 5 MB × 3). All existing `print()` calls in fetchers, runner, and config_loader are replaced with calls to this logger. The MCP server writes `logs/status.json` after every `scrape_jobs` invocation and reads it back in the new `get_scrape_status()` tool.

**Tech Stack:** Python `logging`, `logging.handlers.RotatingFileHandler`, `pytest`, `unittest.mock`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scraper/log.py` | Central logger: name, handlers, idempotency |
| Create | `logs/.gitkeep` | Ensure `logs/` dir exists in repo |
| Create | `tests/test_log.py` | Tests for `get_logger()` |
| Create | `tests/test_status.py` | Tests for `_write_status()` and `get_scrape_status()` |
| Modify | `.gitignore` | Gitignore `logs/status.json` and `logs/*.log` (already has `*.log`) |
| Modify | `scraper/fetchers/base.py` | `print()` → `logger` |
| Modify | `scraper/fetchers/curl_cffi.py` | `print()` → `logger` |
| Modify | `scraper/fetchers/cloudscraper.py` | `print()` → `logger` |
| Modify | `scraper/fetchers/playwright.py` | `print()` → `logger` |
| Modify | `scraper/runner.py` | `print()` → `logger` |
| Modify | `scraper/config_loader.py` | `print()` warnings → `logger.warning` |
| Modify | `mcp_server/server.py` | Add `_STATUS_PATH`, `_LOG_PATH`, `_write_status()`, `get_scrape_status()`, instrument `scrape_jobs()` |

---

## Task 1: Central logger (`scraper/log.py`)

**Files:**
- Create: `scraper/log.py`
- Create: `tests/test_log.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_log.py
from __future__ import annotations

import logging


def test_get_logger_returns_named_logger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib, scraper.log as log_mod
    importlib.reload(log_mod)  # reset module state for isolation

    logger = log_mod.get_logger()
    assert logger.name == "job-scraper"


def test_get_logger_has_two_handlers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib, scraper.log as log_mod
    importlib.reload(log_mod)

    logger = log_mod.get_logger()
    assert len(logger.handlers) == 2


def test_get_logger_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib, scraper.log as log_mod
    importlib.reload(log_mod)

    logger = log_mod.get_logger()
    count = len(logger.handlers)
    log_mod.get_logger()  # second call
    assert len(logger.handlers) == count


def test_get_logger_creates_logs_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib, scraper.log as log_mod
    importlib.reload(log_mod)

    log_mod.get_logger()
    assert (tmp_path / "logs").is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/orangemango/Documents/workspace/private/test/scrap-test
.venv/bin/pytest tests/test_log.py -v
```

Expected: `ModuleNotFoundError: No module named 'scraper.log'`

- [ ] **Step 3: Implement `scraper/log.py`**

```python
# scraper/log.py
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOGGER_NAME = "job-scraper"
_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "scraper.log"
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter(_FMT)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_log.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/log.py tests/test_log.py
git commit -m "feat(logging): add central get_logger() with rotating file handler"
```

---

## Task 2: Gitignore and `logs/` directory

**Files:**
- Modify: `.gitignore`
- Create: `logs/.gitkeep`

- [ ] **Step 1: Add `logs/` entry to `.gitignore`**

Append to `.gitignore` (after the existing `output/*` block):

```
# Logs
logs/*
!logs/.gitkeep
```

Note: `*.log` is already in `.gitignore` globally, but `logs/status.json` is not covered — the `logs/*` line handles it.

- [ ] **Step 2: Create `logs/.gitkeep`**

```bash
touch logs/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore logs/.gitkeep
git commit -m "chore: track logs/ dir, gitignore log artifacts"
```

---

## Task 3: Swap `print()` in fetchers

**Files:**
- Modify: `scraper/fetchers/base.py`
- Modify: `scraper/fetchers/curl_cffi.py`
- Modify: `scraper/fetchers/cloudscraper.py`
- Modify: `scraper/fetchers/playwright.py`

This task is a pure refactor — no behaviour changes. Existing `mcp_server` tests cover the observable outcomes (ok/error in returned dict); no new tests are needed.

- [ ] **Step 1: Update `scraper/fetchers/base.py`**

Replace the two `print(...)` calls inside `FetchChain.fetch`:

```python
# scraper/fetchers/base.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..config import CHALLENGE_MARKERS
from ..log import get_logger

_LOG = get_logger()

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "access denied",
    "security check",
    "verify you are human",
    "checking your browser",
)


def detect_challenge(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if match:
        title = match.group(1).strip()
        lowered = title.lower()
        for marker in _CHALLENGE_TITLES:
            if marker in lowered:
                return f"title={title}"
    if len(html) < 4096:
        for marker in CHALLENGE_MARKERS:
            if marker in html:
                return f"marker={marker}"
    return None


def looks_like_challenge(html: str) -> bool:
    return detect_challenge(html) is not None


@dataclass(frozen=True)
class FetchAttempt:
    fetcher: str
    code: str
    detail: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"fetcher": self.fetcher, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class FetchResult:
    html: str | None
    attempts: tuple[FetchAttempt, ...]


@runtime_checkable
class Fetcher(Protocol):
    name: str

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]: ...


class FetchChain:
    def __init__(self, fetchers: list[Fetcher]) -> None:
        self._fetchers = fetchers

    def fetch(self, url: str) -> FetchResult:
        attempts: list[FetchAttempt] = []
        for fetcher in self._fetchers:
            _LOG.debug("[fetch] trying %s for %s", fetcher.name, url)
            html, attempt = fetcher.fetch(url)
            attempts.append(attempt)
            if html and attempt.code == "ok":
                return FetchResult(html=html, attempts=tuple(attempts))
            _LOG.debug(
                "[fetch] %s insufficient (%s), falling through",
                fetcher.name,
                attempt.code,
            )
        return FetchResult(html=None, attempts=tuple(attempts))
```

- [ ] **Step 2: Update `scraper/fetchers/curl_cffi.py`**

```python
# scraper/fetchers/curl_cffi.py
from __future__ import annotations

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from ..log import get_logger
from .base import FetchAttempt, detect_challenge

CHROME_IMPERSONATE = "chrome131"
_LOG = get_logger()


class CurlCffiFetcher:
    name = "curl_cffi"

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
        except Exception as exc:
            _LOG.warning("[curl_cffi] not installed: %s", exc)
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
            _LOG.error("[curl_cffi] error on %s: %s", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            _LOG.warning("[curl_cffi] %s status=%d", url, status)
            return None, FetchAttempt(
                fetcher=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            _LOG.warning("[curl_cffi] %s blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, FetchAttempt(fetcher=self.name, code="ok")
```

- [ ] **Step 3: Update `scraper/fetchers/cloudscraper.py`**

```python
# scraper/fetchers/cloudscraper.py
from __future__ import annotations

import cloudscraper

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from ..log import get_logger
from .base import FetchAttempt, detect_challenge

_LOG = get_logger()


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
            _LOG.error("[cloudscraper] error on %s: %s", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            _LOG.warning("[cloudscraper] %s status=%d", url, status)
            return None, FetchAttempt(
                fetcher=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            _LOG.warning("[cloudscraper] %s blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, FetchAttempt(fetcher=self.name, code="ok")
```

- [ ] **Step 4: Update `scraper/fetchers/playwright.py`**

```python
# scraper/fetchers/playwright.py
from __future__ import annotations

import time

from ..log import get_logger
from ..config import USER_AGENT
from .base import FetchAttempt, detect_challenge

_LOG = get_logger()


class PlaywrightFetcher:
    name = "playwright"

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            _LOG.warning("[playwright] not installed: %s", exc)
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
            msg = str(exc)
            lowered = msg.lower()
            if "asyncio" in lowered and "loop" in lowered:
                _LOG.error("[playwright] asyncio conflict on %s", url)
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="runtime_error",
                    detail="asyncio sync-API conflict",
                )
            if "timeout" in lowered:
                _LOG.warning("[playwright] timeout on %s", url)
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="timeout",
                    detail=msg[:200],
                )
            _LOG.error("[playwright] error on %s: %s", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {msg[:200]}",
            )

        challenge = detect_challenge(html)
        if challenge:
            _LOG.warning("[playwright] %s blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return html, FetchAttempt(fetcher=self.name, code="ok")
```

- [ ] **Step 5: Run existing tests to confirm no regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all existing tests pass

- [ ] **Step 6: Commit**

```bash
git add scraper/fetchers/base.py scraper/fetchers/curl_cffi.py \
        scraper/fetchers/cloudscraper.py scraper/fetchers/playwright.py
git commit -m "refactor(fetchers): replace print() with structured logger"
```

---

## Task 4: Swap `print()` in `runner.py` and `config_loader.py`

**Files:**
- Modify: `scraper/runner.py`
- Modify: `scraper/config_loader.py`

- [ ] **Step 1: Update `scraper/runner.py`**

Replace all `print(...)` calls. The full updated file:

```python
# scraper/runner.py
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from urllib.parse import urlparse

from .config_loader import ALLOWED_URL_HOSTS, AppConfig, keyword_slug
from .fetchers import (
    CloudscraperFetcher,
    CurlCffiFetcher,
    FetchChain,
    PlaywrightFetcher,
)
from .log import get_logger
from .sites import SCRAPERS, Scraper
from .sites._dates import parse_to_iso
from .sites._filter import apply_filter, project_jobs
from .types import Job

_LOG = get_logger()


def default_fetch_chain() -> FetchChain:
    return FetchChain(
        [CurlCffiFetcher(), CloudscraperFetcher(), PlaywrightFetcher()]
    )


def _enrich_jobs(jobs: list[Job], keyword: str) -> None:
    for job in jobs:
        if job.get("matched_keyword") is None:
            job["matched_keyword"] = keyword
        if job.get("posted_at") is None:
            job["posted_at"] = parse_to_iso(job.get("posted_date"))


def _within_max_age(job: Job, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    raw = job.get("posted_at")
    if not isinstance(raw, str):
        return True
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed >= cutoff


def _fetch_requirements(
    jobs: list[Job],
    fields: frozenset[str],
    fetcher: FetchChain,
    scraper: Scraper,
) -> None:
    if "requirements" not in fields or not jobs:
        return

    def _fetch_one(job: Job) -> str | None:
        url = job.get("url")
        if not url:
            return None
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return None
        if host not in ALLOWED_URL_HOSTS:
            return None
        result = fetcher.fetch(url)
        return scraper.parse_detail(result.html) if result.html else None

    _LOG.info("[%s] fetching requirements for %d job(s)", scraper.name, len(jobs))
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futures = {ex.submit(_fetch_one, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                jobs[idx]["requirements"] = fut.result()
            except Exception:
                jobs[idx]["requirements"] = None


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    output_dir: Path,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
) -> None:
    label = f"{scraper.name}:{keyword_slug(keyword)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{scraper.name}.json"
    debug_path = output_dir / f"{scraper.name}.debug.html"

    _LOG.info("[%s] fetching %s", label, scraper.url)
    result = fetcher.fetch(scraper.url)
    html = result.html
    if not html:
        _LOG.error("[%s] FAILED: no html", label)
        json_path.write_text(
            json.dumps(
                {
                    "error": "fetch failed",
                    "url": scraper.url,
                    "keyword": keyword,
                    "attempts": [a.to_dict() for a in result.attempts],
                },
                indent=2,
            )
        )
        return

    debug_path.write_text(html)
    _LOG.info("[%s] saved raw html → %s (%d bytes)", label, debug_path.name, len(html))

    jobs = scraper.parse(html)
    parsed_count = len(jobs)
    _LOG.info("[%s] parsed %d job(s)", label, parsed_count)

    _enrich_jobs(jobs, keyword)

    cutoff: datetime | None = None
    if max_age_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        before = len(jobs)
        jobs = [j for j in jobs if _within_max_age(j, cutoff)]
        dropped = before - len(jobs)
        _LOG.info(
            "[%s] max_age=%dh kept %d/%d (dropped %d)",
            label,
            max_age_hours,
            len(jobs),
            before,
            dropped,
        )

    if content_filter:
        before = len(jobs)
        jobs = apply_filter(jobs, content_filter)
        dropped = before - len(jobs)
        _LOG.info(
            "[%s] filter=%s kept %d/%d (dropped %d)",
            label,
            content_filter,
            len(jobs),
            before,
            dropped,
        )

    _fetch_requirements(jobs, fields, fetcher, scraper)

    projected = project_jobs(jobs, fields)
    json_path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "fields": sorted(fields),
                "max_age_hours": max_age_hours,
                "filter": content_filter or None,
                "count": len(projected),
                "jobs": projected,
            },
            indent=2,
        )
    )
    _LOG.info("[%s] wrote %s", label, json_path.name)


def _select_targets(config: AppConfig, requested: Iterable[str]) -> list[str]:
    requested_list = list(requested)
    if requested_list:
        return requested_list
    return list(config.enabled_site_names())


def _build_pairs(
    config: AppConfig, sites: list[str], keywords: list[str]
) -> list[tuple[str, str]]:
    return [(keyword, site) for keyword in keywords for site in sites]


def run(
    config: AppConfig,
    targets: Iterable[str] = (),
    output_dir: Path | None = None,
    keywords: Iterable[str] | None = None,
) -> int:
    out = output_dir or config.output_dir
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()

    selected = _select_targets(config, targets)
    if not selected:
        _LOG.error("[runner] no sites selected (none enabled in config and no CLI args)")
        return 1

    unknown = [name for name in selected if name not in SCRAPERS]
    if unknown:
        _LOG.error(
            "[runner] unknown sites: %s. available: %s",
            ", ".join(unknown),
            ", ".join(SCRAPERS),
        )
        return 1

    keyword_list = list(keywords) if keywords else list(config.keywords)
    if not keyword_list:
        _LOG.error("[runner] no keywords to scrape")
        return 1

    pairs = _build_pairs(config, selected, keyword_list)
    fetcher = default_fetch_chain()

    def _process(pair: tuple[str, str]) -> None:
        keyword, name = pair
        site_cfg = config.site(name)
        if site_cfg is None:
            _LOG.warning("[runner] '%s' has no entry in config.yaml; skipping", name)
            return
        scraper_cls = SCRAPERS[name]
        url = site_cfg.url_for(keyword)
        scraper = scraper_cls(url=url, limit=config.limit)
        keyword_dir = out / keyword_slug(keyword)
        if not keyword_dir.resolve().is_relative_to(out):
            _LOG.warning(
                "[runner] keyword '%s' slug escapes output_dir; skipping", keyword
            )
            return
        run_one(
            scraper,
            fetcher,
            keyword_dir,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
            config.filter_for(name),
        )

    workers = max(1, min(config.concurrency, len(pairs)))
    if workers == 1 or len(pairs) == 1:
        for pair in pairs:
            _process(pair)
        return 0

    _LOG.info(
        "[runner] running %d (keyword,site) pair(s) with concurrency=%d",
        len(pairs),
        workers,
    )
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {ex.submit(_process, pair): pair for pair in pairs}
        for fut in as_completed(futures):
            keyword, name = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                _LOG.error(
                    "[%s:%s] thread error: %s", name, keyword_slug(keyword), exc
                )
    return 0
```

- [ ] **Step 2: Update `scraper/config_loader.py`** — swap two `print()` warnings

In `_validate_fields` (line ~171), replace:
```python
            print(
                f"[config] warning: {source} contains unknown field '{entry}'; "
                f"will be ignored. allowed: {sorted(CANONICAL_FIELDS)}",
                file=sys.stderr,
            )
```
With:
```python
            from .log import get_logger as _get_logger
            _get_logger().warning(
                "[config] %s contains unknown field '%s'; ignored. allowed: %s",
                source, entry, sorted(CANONICAL_FIELDS),
            )
```

In `_validate_filter` (line ~212), replace:
```python
            print(
                f"[config] warning: {source} contains unknown filter field "
                f"'{key}'; will be ignored. allowed: {sorted(FILTERABLE_FIELDS)}",
                file=sys.stderr,
            )
```
With:
```python
            from .log import get_logger as _get_logger
            _get_logger().warning(
                "[config] %s contains unknown filter field '%s'; ignored. allowed: %s",
                source, key, sorted(FILTERABLE_FIELDS),
            )
```

Also remove the `import sys` line at the top of `config_loader.py` since it's no longer used.

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all existing tests pass

- [ ] **Step 4: Commit**

```bash
git add scraper/runner.py scraper/config_loader.py
git commit -m "refactor(runner): replace print() with structured logger"
```

---

## Task 5: `_write_status()` helper in `mcp_server/server.py`

**Files:**
- Modify: `mcp_server/server.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: Write failing tests for `_write_status()`**

```python
# tests/test_status.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _ok_result(keyword: str = "engineer", site: str = "glints", count: int = 3) -> dict:
    return {
        "ok": True,
        "keywords": [keyword],
        "requested_sites": [site],
        "exit_code": 0,
        "results": [{"keyword": keyword, "sites": [{"site": site, "count": count}]}],
        "errors": [],
    }


def _err_result(keyword: str = "engineer", site: str = "glints") -> dict:
    return {
        "ok": False,
        "keywords": [keyword],
        "requested_sites": [site],
        "exit_code": 0,
        "results": [{"keyword": keyword, "sites": []}],
        "errors": [{"keyword": keyword, "site": site, "reason": "fetch failed"}],
    }


def test_write_status_creates_file(tmp_path):
    status_path = tmp_path / "status.json"
    with patch("mcp_server.server._STATUS_PATH", status_path):
        from mcp_server.server import _write_status
        _write_status(_ok_result(), 5.1)

    assert status_path.exists()
    data = json.loads(status_path.read_text())
    assert data["last_run"]["ok"] is True
    assert data["last_run"]["total_jobs"] == 3
    assert data["last_run"]["duration_seconds"] == 5.1
    assert data["last_error"] is None
    assert data["per_site"]["glints"]["last_status"] == "ok"
    assert data["per_site"]["glints"]["last_job_count"] == 3


def test_write_status_records_error(tmp_path):
    status_path = tmp_path / "status.json"
    with patch("mcp_server.server._STATUS_PATH", status_path):
        from mcp_server.server import _write_status
        _write_status(_err_result(), 2.0)

    data = json.loads(status_path.read_text())
    assert data["last_run"]["ok"] is False
    assert data["last_run"]["error_count"] == 1
    assert data["last_error"] is not None
    assert data["last_error"]["reason"] == "fetch failed"
    assert data["per_site"]["glints"]["last_status"] == "error"
    assert data["per_site"]["glints"]["last_job_count"] == 0


def test_write_status_merges_existing_per_site(tmp_path):
    status_path = tmp_path / "status.json"
    # Seed with an existing linkedin entry
    status_path.write_text(json.dumps({
        "last_run": {},
        "last_error": None,
        "per_site": {
            "linkedin": {
                "last_run_at": "2026-01-01T00:00:00+00:00",
                "last_status": "ok",
                "last_job_count": 7,
                "last_error": None,
            }
        },
    }))
    with patch("mcp_server.server._STATUS_PATH", status_path):
        from mcp_server.server import _write_status
        _write_status(_ok_result(site="glints"), 3.0)

    data = json.loads(status_path.read_text())
    # Both sites present: glints from this run, linkedin preserved
    assert "linkedin" in data["per_site"]
    assert "glints" in data["per_site"]
    assert data["per_site"]["linkedin"]["last_job_count"] == 7
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_status.py -v
```

Expected: `ImportError` or `AttributeError: module 'mcp_server.server' has no attribute '_write_status'`

- [ ] **Step 3: Add `_STATUS_PATH`, `_LOG_PATH`, and `_write_status()` to `mcp_server/server.py`**

Add after the existing imports at the top of `mcp_server/server.py`:

```python
import time as _time_mod  # rename to avoid collision with existing `time` usage
from datetime import datetime, timezone

from scraper.log import get_logger as _get_logger

_STATUS_PATH = Path("logs/status.json")
_LOG_PATH = Path("logs/scraper.log")
```

Then add `_write_status()` as a module-level private function (before `list_sites`):

```python
def _write_status(result: dict[str, Any], duration: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    errors: list[dict[str, Any]] = result.get("errors", [])

    last_error: dict[str, Any] | None = None
    if errors:
        last_error = {**errors[-1], "timestamp": now}

    per_site: dict[str, Any] = {}
    for kw_result in result.get("results", []):
        for site_entry in kw_result.get("sites", []):
            name = site_entry.get("site")
            if name:
                per_site[name] = {
                    "last_run_at": now,
                    "last_status": "ok",
                    "last_job_count": site_entry.get("count", 0),
                    "last_error": None,
                }
    for err in errors:
        name = err.get("site")
        if name:
            per_site[name] = {
                "last_run_at": now,
                "last_status": "error",
                "last_job_count": 0,
                "last_error": err.get("reason"),
            }

    existing_per_site: dict[str, Any] = {}
    if _STATUS_PATH.exists():
        try:
            existing_per_site = json.loads(_STATUS_PATH.read_text()).get("per_site", {})
        except (json.JSONDecodeError, OSError):
            pass
    merged_per_site = {**existing_per_site, **per_site}

    total_jobs = sum(
        site_entry.get("count", 0)
        for kw_result in result.get("results", [])
        for site_entry in kw_result.get("sites", [])
    )

    status = {
        "last_run": {
            "timestamp": now,
            "ok": result.get("ok", False),
            "duration_seconds": round(duration, 2),
            "keywords": result.get("keywords", []),
            "sites": result.get("requested_sites", []),
            "total_jobs": total_jobs,
            "error_count": len(errors),
            "errors": errors,
        },
        "last_error": last_error,
        "per_site": merged_per_site,
    }

    _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATUS_PATH.write_text(json.dumps(status, indent=2))
```

Note: `mcp_server/server.py` already imports `time` — rename the new import to `_time_mod` is unnecessary. Instead just add `from datetime import datetime, timezone` and the other additions without renaming.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_status.py -v
```

Expected: 3 passed

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add mcp_server/server.py tests/test_status.py
git commit -m "feat(mcp): add _write_status() to persist scrape run state"
```

---

## Task 6: `get_scrape_status()` MCP tool

**Files:**
- Modify: `mcp_server/server.py`
- Modify: `tests/test_status.py`

- [ ] **Step 1: Add tests for `get_scrape_status()`**

Append to `tests/test_status.py`:

```python
def test_get_scrape_status_no_file(tmp_path):
    with patch("mcp_server.server._STATUS_PATH", tmp_path / "status.json"):
        from mcp_server.server import get_scrape_status
        result = get_scrape_status()

    assert result["available"] is False
    assert "message" in result


def test_get_scrape_status_returns_data(tmp_path):
    status_path = tmp_path / "status.json"
    payload = {
        "last_run": {
            "timestamp": "2026-05-10T14:00:00+00:00",
            "ok": True,
            "duration_seconds": 8.5,
            "keywords": ["engineer"],
            "sites": ["glints"],
            "total_jobs": 4,
            "error_count": 0,
            "errors": [],
        },
        "last_error": None,
        "per_site": {
            "glints": {
                "last_run_at": "2026-05-10T14:00:00+00:00",
                "last_status": "ok",
                "last_job_count": 4,
                "last_error": None,
            }
        },
    }
    status_path.write_text(json.dumps(payload))

    with (
        patch("mcp_server.server._STATUS_PATH", status_path),
        patch("mcp_server.server._LOG_PATH", tmp_path / "scraper.log"),
    ):
        from mcp_server.server import get_scrape_status
        result = get_scrape_status()

    assert result["available"] is True
    assert result["last_run"]["ok"] is True
    assert result["last_run"]["total_jobs"] == 4
    assert result["per_site"]["glints"]["last_status"] == "ok"
    assert result["recent_logs"] == []  # no log file exists


def test_get_scrape_status_includes_recent_logs(tmp_path):
    status_path = tmp_path / "status.json"
    log_path = tmp_path / "scraper.log"

    status_path.write_text(json.dumps({
        "last_run": {"ok": True, "total_jobs": 1, "error_count": 0},
        "last_error": None,
        "per_site": {},
    }))
    log_lines = [f"line {i}" for i in range(50)]
    log_path.write_text("\n".join(log_lines))

    with (
        patch("mcp_server.server._STATUS_PATH", status_path),
        patch("mcp_server.server._LOG_PATH", log_path),
    ):
        from mcp_server.server import get_scrape_status
        result = get_scrape_status()

    assert result["available"] is True
    assert len(result["recent_logs"]) == 30
    assert result["recent_logs"][0] == "line 20"  # last 30 of 50
    assert result["recent_logs"][-1] == "line 49"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_status.py::test_get_scrape_status_no_file \
                 tests/test_status.py::test_get_scrape_status_returns_data \
                 tests/test_status.py::test_get_scrape_status_includes_recent_logs -v
```

Expected: `AttributeError: module 'mcp_server.server' has no attribute 'get_scrape_status'`

- [ ] **Step 3: Add `get_scrape_status()` to `mcp_server/server.py`**

Add after `update_config` and before `scrape_jobs`:

```python
@mcp.tool()
def get_scrape_status() -> dict[str, Any]:
    """Return the status of the last scrape_jobs run plus recent log lines.

    Returns:
        dict with keys:
            available: false when no run has been recorded yet
            last_run: {timestamp, ok, duration_seconds, keywords, sites,
                       total_jobs, error_count, errors}
            last_error: last error entry with timestamp, or null if last run clean
            per_site: {site_name: {last_run_at, last_status, last_job_count, last_error}}
            recent_logs: last 30 lines from logs/scraper.log (empty list if no log file)
    """
    if not _STATUS_PATH.exists():
        return {"available": False, "message": "No scrape run has been recorded yet."}

    try:
        status = json.loads(_STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"available": False, "error": f"Could not read status file: {exc}"}

    recent_logs: list[str] = []
    if _LOG_PATH.exists():
        try:
            lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            recent_logs = lines[-30:]
        except OSError:
            pass

    return {"available": True, **status, "recent_logs": recent_logs}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_status.py -v
```

Expected: all test_status tests pass

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add mcp_server/server.py tests/test_status.py
git commit -m "feat(mcp): add get_scrape_status() tool for bot-readable run status"
```

---

## Task 7: Instrument `scrape_jobs()` with logging and status write

**Files:**
- Modify: `mcp_server/server.py`
- Modify: `tests/test_scrape_jobs_ok.py` (add one new test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_scrape_jobs_ok.py`:

```python
from unittest.mock import MagicMock, patch
import json


@patch("mcp_server.server._write_status")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_writes_status(mock_read, mock_load, mock_run, mock_write_status):
    """scrape_jobs must call _write_status exactly once after a run."""
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 1,
        "jobs": [{"title": "A"}],
        "max_age_hours": None,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs
    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_scrape_jobs_ok.py::test_scrape_jobs_writes_status -v
```

Expected: `AssertionError: Expected '_write_status' to be called once.`

- [ ] **Step 3: Update `scrape_jobs()` in `mcp_server/server.py`**

Replace the existing `scrape_jobs` function with:

```python
@mcp.tool()
def scrape_jobs(
    sites: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Run the job scraper and return aggregated results.

    Args:
        sites: optional list of site names to scrape. When omitted, runs every
            site marked enabled in config.yaml.
        keywords: optional list of keywords to scrape. When omitted, runs every
            keyword in config.yaml. Useful to ad-hoc query a single term without
            editing config.yaml.

    Returns:
        dict with keys:
            ok: true when every requested site was reached, regardless of job
                count. Zero jobs with ok=true means the site responded but
                nothing matched your filters or date range — this is normal,
                not an error. ok=false means at least one site failed to fetch.
            keywords: list of keywords actually attempted
            requested_sites: list of site names attempted (per keyword)
            exit_code: scraper exit code (0 = ran without fatal error;
                does NOT reflect per-site fetch success — use ok for that)
            results: list grouped by keyword, each entry:
                {keyword, sites: [{site, fields, count, jobs, ...}]}.
                A site entry is absent from this list when its fetch failed
                (see errors). Each job is projected to the fields configured
                for that site and stamped with `matched_keyword`. Canonical
                fields: site, matched_keyword, title, company, url, location,
                salary, posted_date, posted_at, work_type, employment_type,
                experience_level, job_id, requirements. Fields a site cannot
                extract are returned as null.
            errors: list of {keyword, site, reason, attempts?} for any pair
                that failed. Presence of entries here means ok=false.
                `attempts` (when present) lists per-fetcher outcomes:
                [{fetcher, code, detail}]. Codes:
                  - http_<status>     site rejected request (e.g. http_403)
                  - challenge         anti-bot wall (detail = matched title/marker)
                  - timeout           network or page-load timeout
                  - runtime_error     unexpected exception (detail = class+msg)
                  - not_installed     fetcher dependency missing
    """
    log = _get_logger()
    log.info("scrape_jobs called sites=%s keywords=%s", sites, keywords)
    t_start = time.monotonic()

    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
        log.error("scrape_jobs config error: %s", exc)
        return {"error": str(exc)}

    target_sites = list(sites) if sites else list(config.enabled_site_names())
    target_keywords = list(keywords) if keywords else list(config.keywords)

    exit_code = run_scraper(
        config, targets=target_sites, keywords=target_keywords
    )

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for keyword in target_keywords:
        per_site: list[dict[str, Any]] = []
        for name in target_sites:
            payload = _read_site_output(config, keyword, name)
            if payload is None:
                errors.append(
                    {
                        "keyword": keyword,
                        "site": name,
                        "reason": "missing or invalid output JSON",
                    }
                )
                continue
            if isinstance(payload, dict) and "error" in payload:
                err: dict[str, Any] = {
                    "keyword": keyword,
                    "site": name,
                    "reason": str(payload.get("error")),
                }
                attempts = payload.get("attempts")
                if isinstance(attempts, list):
                    err["attempts"] = attempts
                errors.append(err)
                continue
            per_site.append({"site": name, **payload})
        results.append({"keyword": keyword, "sites": per_site})

    total_jobs = sum(
        s.get("count", 0) for r in results for s in r.get("sites", [])
    )
    result = {
        "ok": len(errors) == 0,
        "keywords": target_keywords,
        "requested_sites": target_sites,
        "exit_code": exit_code,
        "results": results,
        "errors": errors,
    }

    duration = time.monotonic() - t_start
    log.info(
        "scrape_jobs done ok=%s errors=%d jobs=%d duration=%.1fs",
        result["ok"],
        len(errors),
        total_jobs,
        duration,
    )

    _write_status(result, duration)

    return result
```

Also add `import time` to the top of `mcp_server/server.py` if not already present (it already is — used for backup timestamps).

Add these imports to the top of `mcp_server/server.py`:

```python
from datetime import datetime, timezone
from scraper.log import get_logger as _get_logger
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_scrape_jobs_ok.py -v
```

Expected: all 5 tests pass (4 existing + 1 new)

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add mcp_server/server.py tests/test_scrape_jobs_ok.py
git commit -m "feat(mcp): instrument scrape_jobs with logging and status write"
```

---

## Self-Review

**Spec coverage:**
- [x] Central logger with file + stderr handlers → Task 1
- [x] `logs/.gitkeep` + gitignore → Task 2
- [x] Fetchers: `print()` → logger → Task 3
- [x] Runner + config_loader: `print()` → logger → Task 4
- [x] `_write_status()` with last_run, last_error, per_site → Task 5
- [x] `get_scrape_status()` MCP tool with recent_logs → Task 6
- [x] `scrape_jobs()` logs entry/exit + calls `_write_status()` → Task 7

**Placeholder scan:** No TBDs, TODOs, or "implement later" phrases found. All code blocks are complete.

**Type consistency:**
- `_write_status(result: dict[str, Any], duration: float)` — called identically in Task 5 tests and Task 7 implementation.
- `_STATUS_PATH: Path` — monkeypatched consistently across Task 5 and Task 6 tests.
- `_LOG_PATH: Path` — monkeypatched consistently in Task 6 tests.
- `get_scrape_status()` returns `dict[str, Any]` — matches test assertions throughout.
