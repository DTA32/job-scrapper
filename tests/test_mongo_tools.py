# tests/test_mongo_tools.py
from __future__ import annotations

from unittest.mock import patch

from mcp_server.server import get_latest_scrape_run, insert_scrape_run


def test_insert_scrape_run_ok():
    with patch("mcp_server.mongo.insert_run", return_value="abc123") as mock_insert:
        result = insert_scrape_run({"foo": "bar"})
    assert result == {"ok": True, "inserted_id": "abc123"}
    mock_insert.assert_called_once_with({"foo": "bar"})


def test_insert_scrape_run_error():
    with patch("mcp_server.mongo.insert_run", side_effect=Exception("connection refused")):
        result = insert_scrape_run({"foo": "bar"})
    assert result["ok"] is False
    assert "connection refused" in result["error"]


def test_get_latest_scrape_run_no_data():
    with patch("mcp_server.mongo.get_latest_run", return_value=None):
        result = get_latest_scrape_run()
    assert result["available"] is False
    assert "message" in result


def test_get_latest_scrape_run_returns_data():
    doc = {
        "_id": "abc123",
        "_created_at": "2026-05-28T00:00:00+00:00",
        "run_metadata": {"ok": True},
        "bot_post_status": {"total_posted": 5, "failed": 0},
    }
    with patch("mcp_server.mongo.get_latest_run", return_value=doc):
        result = get_latest_scrape_run()
    assert result["available"] is True
    assert result["run_metadata"]["ok"] is True
    assert result["bot_post_status"]["total_posted"] == 5


def test_get_latest_scrape_run_error():
    with patch("mcp_server.mongo.get_latest_run", side_effect=Exception("timeout")):
        result = get_latest_scrape_run()
    assert result["available"] is False
    assert "timeout" in result["error"]
