from __future__ import annotations

from typing import TypedDict


class Job(TypedDict):
    site: str
    title: str
    company: str
    location: str | None
    url: str | None
