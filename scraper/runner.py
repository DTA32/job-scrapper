from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .config_loader import AppConfig, keyword_slug
from .fetchers import CloudscraperFetcher, FetchChain, PlaywrightFetcher
from .sites import SCRAPERS, Scraper
from .sites._dates import parse_to_iso
from .sites._filter import project_jobs
from .types import Job


def default_fetch_chain() -> FetchChain:
    return FetchChain([CloudscraperFetcher(), PlaywrightFetcher()])


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


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    output_dir: Path,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
) -> None:
    label = f"{scraper.name}:{keyword_slug(keyword)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{scraper.name}.json"
    debug_path = output_dir / f"{scraper.name}.debug.html"

    print(f"[{label}] fetching {scraper.url}")
    html = fetcher.fetch(scraper.url)
    if not html:
        print(f"[{label}] FAILED: no html", file=sys.stderr)
        json_path.write_text(
            json.dumps(
                {"error": "fetch failed", "url": scraper.url, "keyword": keyword},
                indent=2,
            )
        )
        return

    debug_path.write_text(html)
    print(f"[{label}] saved raw html → {debug_path.name} ({len(html)} bytes)")

    jobs = scraper.parse(html)
    parsed_count = len(jobs)
    print(f"[{label}] parsed {parsed_count} job(s)")

    _enrich_jobs(jobs, keyword)

    cutoff: datetime | None = None
    if max_age_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        before = len(jobs)
        jobs = [j for j in jobs if _within_max_age(j, cutoff)]
        dropped = before - len(jobs)
        print(
            f"[{label}] max_age={max_age_hours}h kept {len(jobs)}/{before} "
            f"(dropped {dropped})"
        )

    projected = project_jobs(jobs, fields)
    json_path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "fields": sorted(fields),
                "max_age_hours": max_age_hours,
                "count": len(projected),
                "jobs": projected,
            },
            indent=2,
        )
    )
    print(f"[{label}] wrote {json_path.name}")


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
        print(
            "[runner] no sites selected (none enabled in config and no CLI args)",
            file=sys.stderr,
        )
        return 1

    unknown = [name for name in selected if name not in SCRAPERS]
    if unknown:
        print(
            f"[runner] unknown sites: {', '.join(unknown)}. "
            f"available: {', '.join(SCRAPERS)}",
            file=sys.stderr,
        )
        return 1

    keyword_list = list(keywords) if keywords else list(config.keywords)
    if not keyword_list:
        print("[runner] no keywords to scrape", file=sys.stderr)
        return 1

    pairs = _build_pairs(config, selected, keyword_list)
    fetcher = default_fetch_chain()

    def _process(pair: tuple[str, str]) -> None:
        keyword, name = pair
        site_cfg = config.site(name)
        if site_cfg is None:
            print(
                f"[runner] '{name}' has no entry in config.yaml; skipping",
                file=sys.stderr,
            )
            return
        scraper_cls = SCRAPERS[name]
        url = site_cfg.url_for(keyword)
        scraper = scraper_cls(url=url, limit=config.limit)
        keyword_dir = out / keyword_slug(keyword)
        run_one(
            scraper,
            fetcher,
            keyword_dir,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
        )

    workers = max(1, min(config.concurrency, len(pairs)))
    if workers == 1 or len(pairs) == 1:
        for pair in pairs:
            _process(pair)
        return 0

    print(
        f"[runner] running {len(pairs)} (keyword,site) pair(s) "
        f"with concurrency={workers}",
        file=sys.stderr,
    )
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {ex.submit(_process, pair): pair for pair in pairs}
        for fut in as_completed(futures):
            keyword, name = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                print(
                    f"[{name}:{keyword_slug(keyword)}] thread error: {exc}",
                    file=sys.stderr,
                )
    return 0
