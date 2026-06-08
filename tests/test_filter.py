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


# --- hierarchy-aware location dispatch (patch the wilayah index) ---

from unittest.mock import patch  # noqa: E402

import scraper.sites._filter as filt  # noqa: E402
from scraper.sites._location import build_index_from_rows  # noqa: E402
from tests.test_location import _ROWS  # noqa: E402

JKT = {"location": ["jakarta", "tangerang", "bandung", "bekasi", "indonesia"]}


def _with_index(rows=_ROWS):
    return patch.object(filt, "get_index", return_value=build_index_from_rows(rows))


def test_district_cakung_kept():
    with _with_index():
        assert filt.filter_reason(_job("Cakung"), JKT) is None


def test_district_tanjung_priok_kept():
    with _with_index():
        assert filt.filter_reason(_job("Tanjung Priok"), JKT) is None


def test_area_dki_jakarta_kept():
    with _with_index():
        assert filt.filter_reason(_job("Area DKI Jakarta"), JKT) is None


def test_jakarta_raya_alias_kept():
    with _with_index():
        assert filt.filter_reason(_job("Jakarta Raya"), JKT) is None


def test_jakarta_raya_indonesia_compound_kept():
    with _with_index():
        assert filt.filter_reason(_job("Jakarta Raya, Indonesia"), JKT) is None


def test_indonesia_literal_kept():
    with _with_index():
        assert filt.filter_reason(_job("Indonesia"), JKT) is None


def test_surabaya_indonesia_dropped():
    with _with_index():
        assert filt.filter_reason(_job("Surabaya, Indonesia"), JKT) is not None


def test_jakarta_baru_dropped():  # Maluku village not in index -> unresolved -> drop
    with _with_index():
        assert filt.filter_reason(_job("Jakarta Baru"), JKT) is not None


def test_surabaya_dropped():
    with _with_index():
        assert filt.filter_reason(_job("Surabaya"), JKT) is not None


def test_yogyakarta_dropped():
    with _with_index():
        assert filt.filter_reason(_job("Yogyakarta dan Sekitarnya"), JKT) is not None


def test_tangerang_selatan_kept():
    with _with_index():
        assert filt.filter_reason(_job("Tangerang Selatan"), JKT) is None


def test_kabupaten_bandung_kept():
    with _with_index():
        assert filt.filter_reason(_job("Kabupaten Bandung"), JKT) is None


def test_null_location_kept_with_index():  # existing semantics preserved
    with _with_index():
        assert filt.filter_reason(_job(None), JKT) is None


def test_other_keys_still_substring():
    with _with_index():
        job = _job("Jakarta")
        job["employment_type"] = "Full-time"
        assert filt.filter_reason(job, {"employment_type": ["full-time"]}) is None


def test_legacy_fallback_when_index_none():
    with patch.object(filt, "get_index", return_value=None):
        assert filt.filter_reason(_job("Jakarta Selatan"), {"location": ["jakarta"]}) is None
        assert filt.filter_reason(_job("Surabaya"), {"location": ["jakarta"]}) is not None
