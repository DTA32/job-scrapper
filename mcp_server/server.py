from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from scraper.config_loader import AppConfig, ConfigError, keyword_slug, load
from scraper.runner import run as run_scraper

DEFAULT_CONFIG_PATH = Path(os.environ.get("SCRAPER_CONFIG", "config.yaml"))
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8080"))

mcp = FastMCP("job-scraper", host=HOST, port=PORT)


def _load_config(path: Path) -> AppConfig:
    return load(path)


def _read_site_output(
    config: AppConfig, keyword: str, name: str
) -> dict[str, Any] | None:
    path = config.output_dir / keyword_slug(keyword) / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _deep_merge(base: dict, patch: dict) -> dict:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _atomic_write_yaml(path: Path, data: dict) -> None:
    serialized = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(serialized)
    tmp_path.replace(path)


@mcp.tool()
def list_sites() -> dict[str, Any]:
    """List sites declared in config.yaml with their enabled status.

    Each site shows its raw url_template plus a sample resolved URL formatted
    against the first configured keyword. The full keyword list is also returned.
    """
    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
        return {"error": str(exc)}
    sample_keyword = config.keywords[0] if config.keywords else ""
    return {
        "keywords": list(config.keywords),
        "limit": config.limit,
        "sites": [
            {
                "name": site.name,
                "enabled": site.enabled,
                "url_template": site.url_template,
                "sample_url": (
                    site.url_for(sample_keyword) if sample_keyword else None
                ),
            }
            for site in config.sites
        ],
    }


@mcp.tool()
def get_config() -> dict[str, Any]:
    """Return the current config.yaml contents as a parsed dict.

    Use this before update_config to inspect the current shape, then send a
    minimal patch to change only what you want.
    """
    if not DEFAULT_CONFIG_PATH.exists():
        return {"error": f"config file not found: {DEFAULT_CONFIG_PATH}"}
    try:
        raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    except yaml.YAMLError as exc:
        return {"error": f"invalid YAML: {exc}"}
    return raw if isinstance(raw, dict) else {}


@mcp.tool()
def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge a patch into config.yaml after validating the result.

    The patch is merged into the existing config (nested dicts are merged
    recursively; lists and scalars are replaced). The merged document is
    validated using the same loader the scraper itself uses; on validation
    failure, the file is left untouched and the error is returned.

    A timestamped backup (config.yaml.bak.<unix-ts>) is created before the
    new file is written atomically.

    Args:
        patch: dict to merge in. Examples:
            {"keyword": "data analyst"}
            {"max_age_hours": 24}
            {"sites": {"linkedin": {"enabled": false}}}
            {"sites": {"glints": {"max_age_hours": 12}}}

    Returns:
        On success: {ok: True, applied: <merged>, backup: <path>}
        On failure: {ok: False, error: <reason>}
    """
    if not isinstance(patch, dict):
        return {"ok": False, "error": "patch must be a dict"}
    if not DEFAULT_CONFIG_PATH.exists():
        return {"ok": False, "error": f"config file not found: {DEFAULT_CONFIG_PATH}"}

    try:
        current = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text()) or {}
    except yaml.YAMLError as exc:
        return {"ok": False, "error": f"invalid YAML in current config: {exc}"}
    if not isinstance(current, dict):
        return {"ok": False, "error": "current config root must be a mapping"}

    merged = _deep_merge(current, patch)

    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fh:
        yaml.safe_dump(merged, fh, sort_keys=False, allow_unicode=True)
        validation_tmp = Path(fh.name)
    try:
        load(validation_tmp)
    except ConfigError as exc:
        validation_tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"validation failed: {exc}"}
    finally:
        validation_tmp.unlink(missing_ok=True)

    backup_path = DEFAULT_CONFIG_PATH.with_name(
        f"{DEFAULT_CONFIG_PATH.name}.bak.{int(time.time())}"
    )
    try:
        shutil.copy2(DEFAULT_CONFIG_PATH, backup_path)
    except OSError as exc:
        return {"ok": False, "error": f"backup failed: {exc}"}

    try:
        _atomic_write_yaml(DEFAULT_CONFIG_PATH, merged)
    except OSError as exc:
        return {"ok": False, "error": f"write failed: {exc}"}

    return {"ok": True, "applied": merged, "backup": str(backup_path)}


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
            keywords: list of keywords actually attempted
            requested_sites: list of site names attempted (per keyword)
            exit_code: scraper exit code
            results: list grouped by keyword, each entry:
                {keyword, sites: [{site, fields, count, jobs, ...}]}.
                Each job is projected to the fields configured for that site
                and stamped with `matched_keyword`. Canonical fields:
                  site, matched_keyword, title, company, url, location,
                  salary, posted_date, posted_at, work_type,
                  employment_type, experience_level, job_id.
                Fields a site cannot extract are returned as null.
            errors: list of {keyword, site, reason} for any pair that failed
    """
    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
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
                errors.append(
                    {
                        "keyword": keyword,
                        "site": name,
                        "reason": str(payload.get("error")),
                    }
                )
                continue
            per_site.append({"site": name, **payload})
        results.append({"keyword": keyword, "sites": per_site})

    return {
        "keywords": target_keywords,
        "requested_sites": target_sites,
        "exit_code": exit_code,
        "results": results,
        "errors": errors,
    }


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
