from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

from .config_loader import AppConfig
from .fetchers import CloudscraperFetcher, FetchChain, PlaywrightFetcher
from .sites import SCRAPERS, Scraper


def default_fetch_chain() -> FetchChain:
    return FetchChain([CloudscraperFetcher(), PlaywrightFetcher()])


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    output_dir: Path,
    keyword: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{scraper.name}.json"
    debug_path = output_dir / f"{scraper.name}.debug.html"

    print(f"[{scraper.name}] fetching {scraper.url}")
    html = fetcher.fetch(scraper.url)
    if not html:
        print(f"[{scraper.name}] FAILED: no html", file=sys.stderr)
        json_path.write_text(
            json.dumps({"error": "fetch failed", "url": scraper.url}, indent=2)
        )
        return

    debug_path.write_text(html)
    print(
        f"[{scraper.name}] saved raw html → {debug_path.name} ({len(html)} bytes)"
    )

    jobs = scraper.parse(html)
    print(f"[{scraper.name}] parsed {len(jobs)} job(s)")
    json_path.write_text(
        json.dumps(
            {"keyword": keyword, "count": len(jobs), "jobs": jobs},
            indent=2,
        )
    )
    print(f"[{scraper.name}] wrote {json_path.name}")


def _select_targets(config: AppConfig, requested: Iterable[str]) -> list[str]:
    requested_list = list(requested)
    if requested_list:
        return requested_list
    return list(config.enabled_site_names())


def run(
    config: AppConfig,
    targets: Iterable[str] = (),
    output_dir: Path | None = None,
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

    fetcher = default_fetch_chain()
    for name in selected:
        site_cfg = config.site(name)
        if site_cfg is None:
            print(
                f"[runner] '{name}' has no entry in config.yaml; skipping",
                file=sys.stderr,
            )
            continue
        scraper_cls = SCRAPERS[name]
        scraper = scraper_cls(url=site_cfg.url, limit=config.limit)
        run_one(scraper, fetcher, out, config.keyword)
    return 0
