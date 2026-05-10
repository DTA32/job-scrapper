# tests/test_status.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _ok_result(keyword: str = "engineer", site: str = "glints", count: int = 3) -> dict:
    return {
        "ok": True,
        "keywords": [keyword],
        "requested_sites": [site],
        "exit_code": 0,
        "results": [{"keyword": keyword, "sites": [{"site": site, "count": count}]}],
        "errors": [],
    }


def _err_result(keyword: str = "engineer", site: str = "glints") -> dict:
    return {
        "ok": False,
        "keywords": [keyword],
        "requested_sites": [site],
        "exit_code": 0,
        "results": [{"keyword": keyword, "sites": []}],
        "errors": [{"keyword": keyword, "site": site, "reason": "fetch failed"}],
    }


def test_write_status_creates_file(tmp_path):
    status_path = tmp_path / "status.json"
    with patch("mcp_server.server._STATUS_PATH", status_path):
        from mcp_server.server import _write_status
        _write_status(_ok_result(), 5.1)

    assert status_path.exists()
    data = json.loads(status_path.read_text())
    assert data["last_run"]["ok"] is True
    assert data["last_run"]["total_jobs"] == 3
    assert data["last_run"]["duration_seconds"] == 5.1
    assert data["last_error"] is None
    assert data["per_site"]["glints"]["last_status"] == "ok"
    assert data["per_site"]["glints"]["last_job_count"] == 3


def test_write_status_records_error(tmp_path):
    status_path = tmp_path / "status.json"
    with patch("mcp_server.server._STATUS_PATH", status_path):
        from mcp_server.server import _write_status
        _write_status(_err_result(), 2.0)

    data = json.loads(status_path.read_text())
    assert data["last_run"]["ok"] is False
    assert data["last_run"]["error_count"] == 1
    assert data["last_error"] is not None
    assert data["last_error"]["reason"] == "fetch failed"
    assert data["per_site"]["glints"]["last_status"] == "error"
    assert data["per_site"]["glints"]["last_job_count"] == 0


def test_write_status_merges_existing_per_site(tmp_path):
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps({
        "last_run": {},
        "last_error": None,
        "per_site": {
            "linkedin": {
                "last_run_at": "2026-01-01T00:00:00+00:00",
                "last_status": "ok",
                "last_job_count": 7,
                "last_error": None,
            }
        },
    }))
    with patch("mcp_server.server._STATUS_PATH", status_path):
        from mcp_server.server import _write_status
        _write_status(_ok_result(site="glints"), 3.0)

    data = json.loads(status_path.read_text())
    assert "linkedin" in data["per_site"]
    assert "glints" in data["per_site"]
    assert data["per_site"]["linkedin"]["last_job_count"] == 7


def test_get_scrape_status_no_file(tmp_path):
    with patch("mcp_server.server._STATUS_PATH", tmp_path / "status.json"):
        from mcp_server.server import get_scrape_status
        result = get_scrape_status()

    assert result["available"] is False
    assert "message" in result


def test_get_scrape_status_returns_data(tmp_path):
    status_path = tmp_path / "status.json"
    payload = {
        "last_run": {
            "timestamp": "2026-05-10T14:00:00+00:00",
            "ok": True,
            "duration_seconds": 8.5,
            "keywords": ["engineer"],
            "sites": ["glints"],
            "total_jobs": 4,
            "error_count": 0,
            "errors": [],
        },
        "last_error": None,
        "per_site": {
            "glints": {
                "last_run_at": "2026-05-10T14:00:00+00:00",
                "last_status": "ok",
                "last_job_count": 4,
                "last_error": None,
            }
        },
    }
    status_path.write_text(json.dumps(payload))

    with (
        patch("mcp_server.server._STATUS_PATH", status_path),
        patch("mcp_server.server._LOG_PATH", tmp_path / "scraper.log"),
    ):
        from mcp_server.server import get_scrape_status
        result = get_scrape_status()

    assert result["available"] is True
    assert result["last_run"]["ok"] is True
    assert result["last_run"]["total_jobs"] == 4
    assert result["per_site"]["glints"]["last_status"] == "ok"
    assert result["recent_logs"] == []


def test_get_scrape_status_includes_recent_logs(tmp_path):
    status_path = tmp_path / "status.json"
    log_path = tmp_path / "scraper.log"

    status_path.write_text(json.dumps({
        "last_run": {"ok": True, "total_jobs": 1, "error_count": 0},
        "last_error": None,
        "per_site": {},
    }))
    log_lines = [f"line {i}" for i in range(50)]
    log_path.write_text("\n".join(log_lines))

    with (
        patch("mcp_server.server._STATUS_PATH", status_path),
        patch("mcp_server.server._LOG_PATH", log_path),
    ):
        from mcp_server.server import get_scrape_status
        result = get_scrape_status()

    assert result["available"] is True
    assert len(result["recent_logs"]) == 30
    assert result["recent_logs"][0] == "line 20"
    assert result["recent_logs"][-1] == "line 49"
