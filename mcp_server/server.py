from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from scraper.config_loader import AppConfig, ConfigError, load
from scraper.runner import run as run_scraper

DEFAULT_CONFIG_PATH = Path(os.environ.get("SCRAPER_CONFIG", "config.yaml"))
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8080"))

mcp = FastMCP("job-scraper", host=HOST, port=PORT)


def _load_config(path: Path) -> AppConfig:
    return load(path)


def _read_site_output(config: AppConfig, name: str) -> dict[str, Any] | None:
    path = config.output_dir / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


@mcp.tool()
def list_sites() -> dict[str, Any]:
    """List sites declared in config.yaml with their enabled status."""
    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
        return {"error": str(exc)}
    return {
        "keyword": config.keyword,
        "limit": config.limit,
        "sites": [
            {"name": site.name, "enabled": site.enabled, "url": site.url}
            for site in config.sites
        ],
    }


@mcp.tool()
def scrape_jobs(sites: list[str] | None = None) -> dict[str, Any]:
    """Run the job scraper and return aggregated results.

    Args:
        sites: optional list of site names to scrape. When omitted, runs every
            site marked enabled in config.yaml. CLI-style overrides (e.g.
            disabled sites) work the same as `python -m scraper <name>`.

    Returns:
        dict with keys:
            keyword: search term resolved from config.yaml
            requested: list of site names actually attempted
            results: list of per-site result objects
                ({site, count, jobs, ...}) read from output/<name>.json
            errors: list of {site, reason} for any sites that failed to write
    """
    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
        return {"error": str(exc)}

    targets = list(sites) if sites else list(config.enabled_site_names())
    exit_code = run_scraper(config, targets=targets)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for name in targets:
        payload = _read_site_output(config, name)
        if payload is None:
            errors.append({"site": name, "reason": "missing or invalid output JSON"})
            continue
        if isinstance(payload, dict) and "error" in payload:
            errors.append({"site": name, "reason": str(payload.get("error"))})
            continue
        results.append({"site": name, **payload})

    return {
        "keyword": config.keyword,
        "requested": targets,
        "exit_code": exit_code,
        "results": results,
        "errors": errors,
    }


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
