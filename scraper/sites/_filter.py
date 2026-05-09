from __future__ import annotations

from typing import Any

from ..types import Job


def project_job(job: Job, allowed: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key in allowed}


def project_jobs(jobs: list[Job], allowed: frozenset[str]) -> list[dict[str, Any]]:
    return [project_job(job, allowed) for job in jobs]
