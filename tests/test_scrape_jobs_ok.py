from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_config(keyword: str = "data analyst", site: str = "jobstreet"):
    cfg = MagicMock()
    cfg.keywords = (keyword,)
    cfg.enabled_site_names.return_value = (site,)
    cfg.output_dir = MagicMock()
    return cfg


@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_ok_true_when_zero_jobs(mock_read, mock_load, mock_run):
    """0 jobs returned but fetch succeeded → ok must be True."""
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 0,
        "jobs": [],
        "max_age_hours": 24,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 0


@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_ok_true_when_jobs_found(mock_read, mock_load, mock_run):
    """Jobs found → ok must be True."""
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 2,
        "jobs": [{"title": "A"}, {"title": "B"}],
        "max_age_hours": 24,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 2


@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_ok_false_when_fetch_failed(mock_read, mock_load, mock_run):
    """Fetch failed → ok must be False, error captured, sites list empty."""
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "error": "fetch failed",
        "url": "https://example.com",
        "keyword": "data analyst",
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "fetch failed"
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_ok_false_when_output_missing(mock_read, mock_load, mock_run):
    """Missing output file (None from _read_site_output) → ok False."""
    mock_load.return_value = _make_config()
    mock_read.return_value = None

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["results"][0]["sites"] == []
