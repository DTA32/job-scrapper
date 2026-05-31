from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import dateparser

_PARSER_SETTINGS: dict[str, Any] = {
    "RETURN_AS_TIMEZONE_AWARE": True,
    "TIMEZONE": "timezone.utc",
    "TO_TIMEZONE": "timezone.utc",
    "PREFER_DATES_FROM": "past",
}

_LANGUAGES = ["en", "id"]


def parse_to_iso(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    parsed = dateparser.parse(cleaned, languages=_LANGUAGES, settings=cast(Any, _PARSER_SETTINGS))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def parse_to_datetime(raw: str | None) -> datetime | None:
    iso = parse_to_iso(raw)
    if iso is None:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None
