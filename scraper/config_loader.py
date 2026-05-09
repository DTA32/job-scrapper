from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import yaml

from .types import CANONICAL_FIELDS, MANDATORY_FIELDS

DEFAULT_FIELDS: tuple[str, ...] = ("title", "company", "location", "url")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SiteConfig:
    name: str
    enabled: bool
    url: str
    fields: tuple[str, ...] | None = None

    def effective_fields(self, default: tuple[str, ...]) -> tuple[str, ...]:
        return self.fields if self.fields is not None else default


@dataclass(frozen=True)
class AppConfig:
    keyword: str
    limit: int
    concurrency: int
    output_dir: Path
    default_fields: tuple[str, ...]
    sites: tuple[SiteConfig, ...]

    def site(self, name: str) -> SiteConfig | None:
        for site in self.sites:
            if site.name == name:
                return site
        return None

    def enabled_site_names(self) -> tuple[str, ...]:
        return tuple(site.name for site in self.sites if site.enabled)

    def fields_for(self, site_name: str) -> frozenset[str]:
        cfg = self.site(site_name)
        configured = (
            cfg.effective_fields(self.default_fields)
            if cfg is not None
            else self.default_fields
        )
        return MANDATORY_FIELDS | frozenset(configured)


def _build_template_vars(keyword: str) -> dict[str, str]:
    stripped = keyword.strip()
    return {
        "keyword": quote(stripped),
        "keyword_slug": stripped.lower().replace(" ", "-"),
        "keyword_plus": stripped.replace(" ", "+"),
    }


def _resolve_url(site_name: str, template: str, vars_: dict[str, str]) -> str:
    try:
        return template.format(**vars_)
    except KeyError as exc:
        raise ConfigError(
            f"site '{site_name}' url_template uses unknown placeholder {exc}; "
            f"allowed: {sorted(vars_)}"
        ) from exc


def _validate_fields(raw: object, source: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ConfigError(f"{source} must be a list of field names, got {type(raw).__name__}")

    cleaned: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise ConfigError(f"{source} entries must be strings, got {entry!r}")
        if entry not in CANONICAL_FIELDS:
            print(
                f"[config] warning: {source} contains unknown field '{entry}'; "
                f"will be ignored. allowed: {sorted(CANONICAL_FIELDS)}",
                file=sys.stderr,
            )
            continue
        cleaned.append(entry)
    return tuple(cleaned)


def load(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")

    keyword = raw.get("keyword")
    if not isinstance(keyword, str) or not keyword.strip():
        raise ConfigError("config must define non-empty 'keyword'")

    sites_raw = raw.get("sites")
    if not isinstance(sites_raw, dict) or not sites_raw:
        raise ConfigError("config must define a non-empty 'sites' mapping")

    if "default_fields" in raw:
        default_fields = _validate_fields(raw["default_fields"], "default_fields")
        if not default_fields:
            default_fields = DEFAULT_FIELDS
    else:
        default_fields = DEFAULT_FIELDS

    template_vars = _build_template_vars(keyword)
    sites: list[SiteConfig] = []
    for name, cfg in sites_raw.items():
        if not isinstance(cfg, dict):
            raise ConfigError(f"site '{name}' must be a mapping")
        template = cfg.get("url_template")
        if not isinstance(template, str) or not template:
            raise ConfigError(f"site '{name}' must define non-empty 'url_template'")
        url = _resolve_url(name, template, template_vars)
        enabled = bool(cfg.get("enabled", True))

        site_fields: tuple[str, ...] | None = None
        if "fields" in cfg:
            site_fields = _validate_fields(cfg["fields"], f"sites.{name}.fields")

        sites.append(
            SiteConfig(name=name, enabled=enabled, url=url, fields=site_fields)
        )

    limit_raw = raw.get("limit", 2)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'limit' must be an integer, got {limit_raw!r}") from exc
    if limit < 1:
        raise ConfigError(f"'limit' must be >= 1, got {limit}")

    concurrency_raw = raw.get("concurrency", 2)
    try:
        concurrency = int(concurrency_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"'concurrency' must be an integer, got {concurrency_raw!r}"
        ) from exc
    if concurrency < 1:
        raise ConfigError(f"'concurrency' must be >= 1, got {concurrency}")

    output_dir = Path(str(raw.get("output_dir", "output")))

    return AppConfig(
        keyword=keyword.strip(),
        limit=limit,
        concurrency=concurrency,
        output_dir=output_dir,
        default_fields=default_fields,
        sites=tuple(sites),
    )
