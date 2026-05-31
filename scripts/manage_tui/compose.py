"""Discover docker-compose profiles by parsing the YAML directly.

Parsing the files (rather than shelling out to `docker compose config`) means
the TUI still renders its profile rows when the Docker daemon is down or when
.env interpolation vars are unset. A service with no `profiles:` key (e.g.
output-init) is a plain dependency and is excluded from every profile.
"""

from __future__ import annotations

import yaml

from .model import REPO_ROOT


def parse_profiles(compose_files: tuple[str, ...]) -> dict[str, list[str]]:
    """Return {profile_name: sorted unique service names that declare it}."""
    services = _merged_services(compose_files)
    profile_map: dict[str, list[str]] = {}
    for service_name, body in services.items():
        if not isinstance(body, dict):
            continue
        for profile in body.get("profiles", []) or []:
            profile_map.setdefault(str(profile), []).append(service_name)
    return {profile: sorted(set(svcs)) for profile, svcs in sorted(profile_map.items())}


def _merged_services(compose_files: tuple[str, ...]) -> dict:
    """Per-service shallow merge across files (later files win key-by-key).

    Override files (dev/prod) omit `profiles:`, so the base file's profiles are
    preserved — matching how docker compose layers the definitions.
    """
    merged: dict = {}
    for rel in compose_files:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text()) or {}
        services = data.get("services") or {}
        if not isinstance(services, dict):
            continue
        for name, body in services.items():
            existing = merged.get(name)
            if isinstance(existing, dict) and isinstance(body, dict):
                merged[name] = {**existing, **body}
            else:
                merged[name] = body
    return merged
