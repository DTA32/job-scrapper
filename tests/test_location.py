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
