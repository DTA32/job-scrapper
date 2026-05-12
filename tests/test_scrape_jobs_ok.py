from __future__ import annotations

from unittest.mock import MagicMock, patch

from scraper.types import JOB_FIELD_ORDER


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


@patch("mcp_server.server._write_status")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_writes_status(mock_read, mock_load, mock_run, mock_write_status):
    """scrape_jobs must call _write_status exactly once after a run."""
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 1,
        "jobs": [{"title": "A"}],
        "max_age_hours": None,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs
    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)


@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_normalizes_jobs_to_canonical_schema(
    mock_read, mock_load, mock_run
):
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title", "company", "url"],
        "count": 1,
        "jobs": [
            {
                "title": "Data Analyst",
                "company": "ACME",
                "url": "https://example.com/job/1",
                "extra": "drop-me",
            }
        ],
        "max_age_hours": 24,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])
    site_entry = result["results"][0]["sites"][0]
    job = site_entry["jobs"][0]

    assert set(job.keys()) == set(JOB_FIELD_ORDER)
    assert job["site"] == "jobstreet"
    assert job["matched_keyword"] == "data analyst"
    assert "extra" not in job
    assert site_entry["count"] == 1


def test_get_scrape_response_structure_exposes_canonical_fields():
    from mcp_server.server import get_scrape_response_structure

    out = get_scrape_response_structure()

    assert out["tool"] == "scrape_jobs"
    assert out["job_fields"] == list(JOB_FIELD_ORDER)
    assert out["top_level_fields"] == [
        "ok",
        "keywords",
        "requested_sites",
        "exit_code",
        "results",
        "errors",
    ]
