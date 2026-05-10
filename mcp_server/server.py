from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from scraper.config_loader import AppConfig, ConfigError, keyword_slug, load
from scraper.log import get_logger as _get_logger
from scraper.runner import run as run_scraper

DEFAULT_CONFIG_PATH = Path(os.environ.get("SCRAPER_CONFIG", "config.yaml"))
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8080"))

_STATUS_PATH = Path("logs/status.json")
_LOG_PATH = Path("logs/scraper.log")

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
            {"keywords": ["data analyst"]}
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


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
