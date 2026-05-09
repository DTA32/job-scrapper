from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

from .config import KEYWORD
from .fetchers import CloudscraperFetcher, FetchChain, PlaywrightFetcher
from .sites import SCRAPERS, Scraper

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def default_fetch_chain() -> FetchChain:
    return FetchChain([CloudscraperFetcher(), PlaywrightFetcher()])


def run_one(scraper: Scraper, fetcher: FetchChain, output_dir: Path) -> None:
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
            {"keyword": KEYWORD, "count": len(jobs), "jobs": jobs},
            indent=2,
        )
    )
    print(f"[{scraper.name}] wrote {json_path.name}")


def run(targets: Iterable[str], output_dir: Path | None = None) -> int:
    out = output_dir or OUTPUT_DIR
    fetcher = default_fetch_chain()
    unknown = [name for name in targets if name not in SCRAPERS]
    if unknown:
        print(
            f"[runner] unknown sites: {', '.join(unknown)}. "
            f"available: {', '.join(SCRAPERS)}",
            file=sys.stderr,
        )
        return 1
    for name in targets:
        run_one(SCRAPERS[name](), fetcher, out)
    return 0
