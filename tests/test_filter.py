from __future__ import annotations

from scraper.sites._filter import filter_reason, matches_filter
from scraper.types import empty_job


def _job(location: str | None):
    job = empty_job("glints", "Data Analyst", "Acme")
    job["location"] = location
    return job


def test_filter_reason_none_when_match():
    assert filter_reason(_job("Jakarta Selatan"), {"location": ["jakarta"]}) is None


def test_filter_reason_reports_failing_key_and_value():
    reason = filter_reason(_job("Surabaya"), {"location": ["jakarta", "bekasi"]})
    assert reason is not None
    assert "location" in reason
    assert "Surabaya" in reason


def test_filter_reason_skips_null_field():
    # Missing/None field is kept (conservative) — no reason to drop.
    assert filter_reason(_job(None), {"location": ["jakarta"]}) is None


def test_filter_reason_skips_empty_candidate_list():
    assert filter_reason(_job("Surabaya"), {"location": []}) is None


def test_matches_filter_consistent_with_reason():
    job = _job("Surabaya")
    assert matches_filter(job, {"location": ["jakarta"]}) is False
    assert filter_reason(job, {"location": ["jakarta"]}) is not None
