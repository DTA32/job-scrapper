from __future__ import annotations

from typing import Any

from ..log import get_logger
from ..types import Job
from ._location import (
    WilayahIndex,
    candidate_kodes,
    get_index,
    is_under,
    normalize,
    segments,
    term_to_prefixes,
)

_LOG = get_logger()
_WARNED_LEGACY = False


def project_job(job: Job, allowed: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key in allowed}


def project_jobs(jobs: list[Job], allowed: frozenset[str]) -> list[dict[str, Any]]:
    return [project_job(job, allowed) for job in jobs]


def _warn_legacy_once() -> None:
    global _WARNED_LEGACY
    if not _WARNED_LEGACY:
        _WARNED_LEGACY = True
        _LOG.warning("[filter] wilayah index unavailable; location filter using legacy substring")


def _partition_terms(
    expected_values: list[str], index: WilayahIndex
) -> tuple[frozenset[str], tuple[str, ...]]:
    # Recomputed per call (no cache): the active index is replaced fresh each run
    # by refresh_index(), and scanning ~552 province/city entries is cheap. Caching
    # on id(index) would be unsafe here — a GC'd index's id can be reused.
    prefixes: set[str] = set()
    literals: list[str] = []
    for term in expected_values:
        found = term_to_prefixes(term, index.entries)
        if found:
            prefixes |= found
        else:
            literals.append(normalize(term))
    return frozenset(prefixes), tuple(literals)


def _location_reason(raw: str, actual_lower: str, expected_values: list[str]) -> str | None:
    if not actual_lower:
        return None  # blank location: keep (mirrors null handling)

    index = get_index()
    if index is None:  # genuine load failure -> legacy substring
        _warn_legacy_once()
        if any(e in actual_lower for e in expected_values):
            return None
        return f"location={raw!r} not in {expected_values}"

    prefixes, literals = _partition_terms(expected_values, index)
    kodes = candidate_kodes(raw, index)
    if prefixes and any(is_under(k, prefixes) for k in kodes):
        return None  # (a) under an in-scope region
    if kodes:
        return f"location={raw!r} resolved out of scope, not in {expected_values}"  # (b)
    if literals and any(lit in set(segments(normalize(raw))) for lit in literals):
        return None  # (c) nationwide/remote literal
    return f"location={raw!r} unresolved, not in {expected_values}"


def filter_reason(job: Job, filter_: dict[str, list[str]]) -> str | None:
    """Return None if the job passes, else a short reason for the first failing key.

    The ``location`` key uses the wilayah hierarchy resolver; all other keys keep
    case-insensitive substring matching. Empty candidate lists and null/blank fields
    are skipped (the job is kept).
    """
    for key, expected_values in filter_.items():
        if not expected_values:
            continue
        actual = job.get(key)
        if actual is None:
            continue
        if not isinstance(actual, str):
            actual = str(actual)
        actual_lower = actual.strip().lower()

        if key == "location":
            reason = _location_reason(actual, actual_lower, expected_values)
        elif any(expected in actual_lower for expected in expected_values):
            reason = None
        else:
            reason = f"{key}={actual!r} not in {expected_values}"

        if reason is not None:
            return reason
    return None


def matches_filter(job: Job, filter_: dict[str, list[str]]) -> bool:
    return filter_reason(job, filter_) is None


def apply_filter(jobs: list[Job], filter_: dict[str, list[str]]) -> list[Job]:
    if not filter_:
        return jobs
    return [job for job in jobs if matches_filter(job, filter_)]
