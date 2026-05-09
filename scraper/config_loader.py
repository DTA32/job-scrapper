from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SiteConfig:
    name: str
    enabled: bool
    url: str


@dataclass(frozen=True)
class AppConfig:
    keyword: str
    limit: int
    concurrency: int
    output_dir: Path
    sites: tuple[SiteConfig, ...]

    def site(self, name: str) -> SiteConfig | None:
        for site in self.sites:
            if site.name == name:
                return site
        return None

    def enabled_site_names(self) -> tuple[str, ...]:
        return tuple(site.name for site in self.sites if site.enabled)


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
        sites.append(SiteConfig(name=name, enabled=enabled, url=url))

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
        sites=tuple(sites),
    )
