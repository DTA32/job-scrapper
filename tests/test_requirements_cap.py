from __future__ import annotations

from pathlib import Path

from scraper.config_loader import load
from scraper.runner import _cap_requirements

_CONFIG = """
keywords: [software engineer]
requirements_max_chars: 40
sites:
  glints:
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
"""


def _load(tmp_path: Path, body: str = _CONFIG):
    p = tmp_path / "config.yaml"
    p.write_text(body)
    return load(p)


def test_cap_is_parsed(tmp_path: Path):
    assert _load(tmp_path).requirements_max_chars == 40


def test_cap_defaults_to_none(tmp_path: Path):
    body = _CONFIG.replace("requirements_max_chars: 40\n", "")
    assert _load(tmp_path, body).requirements_max_chars is None


def test_short_text_is_untouched():
    assert _cap_requirements("## Requirements\n- Python", 40) == "## Requirements\n- Python"


def test_cut_lands_on_a_line_boundary():
    text = "## Requirements\n- Python\n- Three years of production SQL experience"
    assert _cap_requirements(text, 30) == "## Requirements\n- Python\n…"


def test_single_long_line_is_hard_cut():
    assert _cap_requirements("x" * 100, 40) == "x" * 40 + "\n…"


def test_no_cap_means_no_truncation():
    assert _cap_requirements("x" * 5000, None) == "x" * 5000


def test_blank_or_non_string_becomes_none():
    assert _cap_requirements(None, 40) is None
    assert _cap_requirements(123, 40) is None
    assert _cap_requirements("  \n ", 40) is None
