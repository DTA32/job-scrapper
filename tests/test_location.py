from __future__ import annotations

from scraper.sites._location import is_under, normalize, segments, strip_qualifiers


def test_normalize_collapses_ws_and_lowercases():
    assert normalize("  Kota Administrasi Jakarta Utara ") == "kota administrasi jakarta utara"


def test_strip_leading_qualifiers_iteratively():
    assert strip_qualifiers("area dki jakarta") == "jakarta"
    assert strip_qualifiers("kecamatan tanjung priok") == "tanjung priok"
    assert strip_qualifiers("daerah khusus ibukota jakarta") == "jakarta"


def test_strip_trailing_qualifier():
    assert strip_qualifiers("yogyakarta dan sekitarnya") == "yogyakarta"


def test_strip_guard_never_returns_empty():
    assert strip_qualifiers("kota") == "kota"  # bare qualifier kept, not emptied


def test_segments_splits_on_comma_and_slash():
    assert segments("jakarta raya, indonesia") == ["jakarta raya", "indonesia"]
    assert segments("bandung / jawa barat") == ["bandung", "jawa barat"]


def test_is_under_is_segment_safe():
    assert is_under("31.75.06", {"31"}) is True
    assert is_under("31", {"31"}) is True
    assert is_under("310", {"31"}) is False  # NOT raw startswith
    assert is_under("32.73", {"31"}) is False


from scraper.sites._location import (  # noqa: E402
    WilayahIndex,
    build_index_from_rows,
    candidate_kodes,
    location_in_scope,
    term_to_prefixes,
)

# Rows mirror real wilayah data (kode, nama). Includes the Banten "Cakung"
# VILLAGE (3 dots) to prove villages are excluded from the index.
_ROWS = [
    ("31", "Daerah Khusus Ibukota Jakarta"),
    ("31.71", "Kota Administrasi Jakarta Pusat"),
    ("31.72", "Kota Administrasi Jakarta Utara"),
    ("31.73", "Kota Administrasi Jakarta Barat"),
    ("31.74", "Kota Administrasi Jakarta Selatan"),
    ("31.75", "Kota Administrasi Jakarta Timur"),
    ("31.72.02", "Tanjung Priok"),
    ("31.75.06", "Cakung"),
    ("36", "Banten"),
    ("36.71", "Kota Tangerang"),
    ("36.03", "Kabupaten Tangerang"),
    ("36.74", "Kota Tangerang Selatan"),
    ("36.71.01", "Tangerang"),  # district named Tangerang
    ("36.04.18.2002", "Cakung"),  # Banten VILLAGE collision (3 dots)
    ("32.73", "Kota Bandung"),
    ("32.04", "Kabupaten Bandung"),
    ("32.17", "Kabupaten Bandung Barat"),
    ("32.75", "Kota Bekasi"),
    ("32.16", "Kabupaten Bekasi"),
    ("35.78", "Kota Surabaya"),
    ("34", "Daerah Istimewa Yogyakarta"),
    ("35.71.02", "Kota"),  # bare-qualifier edge
]


def _idx() -> WilayahIndex:
    return build_index_from_rows(_ROWS)


def test_villages_excluded_cakung_resolves_to_jakarta_only():
    assert candidate_kodes("Cakung", _idx()) == {"31.75.06"}  # Banten village gone


def test_resolve_area_dki_jakarta():
    assert candidate_kodes("Area DKI Jakarta", _idx()) == {"31"}


def test_resolve_bare_jakarta_to_province():
    assert candidate_kodes("Jakarta", _idx()) == {"31"}


def test_resolve_kecamatan_prefix():
    assert candidate_kodes("Kecamatan Tanjung Priok", _idx()) == {"31.72.02"}


def test_resolve_alias_jakarta_raya():
    assert candidate_kodes("Jakarta Raya", _idx()) == {"31"}


def test_term_to_prefixes_jakarta_is_province():
    assert term_to_prefixes("jakarta", _idx().entries) == {"31"}


def test_term_to_prefixes_tangerang_three_cities():
    assert term_to_prefixes("tangerang", _idx().entries) == {"36.71", "36.03", "36.74"}


def test_term_to_prefixes_bandung_three():
    assert term_to_prefixes("bandung", _idx().entries) == {"32.73", "32.04", "32.17"}


def test_term_to_prefixes_indonesia_is_literal():
    assert term_to_prefixes("indonesia", _idx().entries) is None


def test_location_in_scope_true_false():
    idx = _idx()
    pj = term_to_prefixes("jakarta", idx.entries)
    assert pj is not None
    assert location_in_scope("Tanjung Priok", idx, pj) is True
    assert location_in_scope("Surabaya", idx, pj) is False


from unittest.mock import patch  # noqa: E402

import scraper.sites._location as loc  # noqa: E402


def test_refresh_index_loads_and_get_returns_it():
    fake = build_index_from_rows(_ROWS)
    try:
        with patch.object(loc, "load_index_from_mongo", return_value=fake):
            assert loc.refresh_index() is fake
        assert loc.get_index() is fake
    finally:
        loc.reset_index()


def test_refresh_index_reloads_fresh_each_run():
    a = build_index_from_rows(_ROWS)
    b = build_index_from_rows(_ROWS)
    try:
        with patch.object(loc, "load_index_from_mongo", side_effect=[a, b]):
            loc.refresh_index()
            assert loc.get_index() is a
            loc.refresh_index()
            assert loc.get_index() is b  # fresh each run, not the stale first load
    finally:
        loc.reset_index()


def test_refresh_index_none_on_failure_degrades():
    try:
        with patch.object(loc, "load_index_from_mongo", return_value=None):
            assert loc.refresh_index() is None
        assert loc.get_index() is None
    finally:
        loc.reset_index()
