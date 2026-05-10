from __future__ import annotations

from typing import TypedDict


class Job(TypedDict):
    site: str
    matched_keyword: str | None
    title: str
    company: str
    url: str | None
    location: str | None
    salary: str | None
    posted_date: str | None
    posted_at: str | None
    work_type: str | None
    employment_type: str | None
    experience_level: str | None
    job_id: str | None
    requirements: str | None


CANONICAL_FIELDS: frozenset[str] = frozenset(
    {
        "site",
        "matched_keyword",
        "title",
        "company",
        "url",
        "location",
        "salary",
        "posted_date",
        "posted_at",
        "work_type",
        "employment_type",
        "experience_level",
        "job_id",
        "requirements",
    }
)

MANDATORY_FIELDS: frozenset[str] = frozenset(
    {"site", "matched_keyword", "title", "company", "url"}
)


def empty_job(site: str, title: str, company: str) -> Job:
    return Job(
        site=site,
        matched_keyword=None,
        title=title,
        company=company,
        url=None,
        location=None,
        salary=None,
        posted_date=None,
        posted_at=None,
        work_type=None,
        employment_type=None,
        experience_level=None,
        job_id=None,
        requirements=None,
    )
