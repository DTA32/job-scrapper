from __future__ import annotations

from typing import Any

from ..types import Job


def project_job(job: Job, allowed: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key in allowed}


def project_jobs(jobs: list[Job], allowed: frozenset[str]) -> list[dict[str, Any]]:
    return [project_job(job, allowed) for job in jobs]


def filter_reason(job: Job, filter_: dict[str, list[str]]) -> str | None:
    """Return None if the job passes the filter, else a short reason for the
    first failing key (e.g. ``"location='Surabaya' not in ['jakarta', 'bekasi']"``).

    Mirrors ``matches_filter`` semantics: empty candidate lists and null/missing
    fields are skipped (the job is kept).
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
        if not any(expected in actual_lower for expected in expected_values):
            return f"{key}={actual!r} not in {expected_values}"
    return None


def matches_filter(job: Job, filter_: dict[str, list[str]]) -> bool:
    return filter_reason(job, filter_) is None


def apply_filter(jobs: list[Job], filter_: dict[str, list[str]]) -> list[Job]:
    if not filter_:
        return jobs
    return [job for job in jobs if matches_filter(job, filter_)]
