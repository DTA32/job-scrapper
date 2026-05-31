# tests/test_health.py
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import mcp_server.mongo as mongo_module
from mcp_server.server import health_check


def _call_health():
    # /health ignores the request object; a stub is enough.
    return asyncio.run(health_check(MagicMock()))


def test_health_ok_when_mongo_reachable():
    with patch.object(mongo_module, "ping", MagicMock()):
        resp = _call_health()
    assert resp.status_code == 200
    assert json.loads(resp.body) == {"status": "ok", "mongo": "ok"}


def test_health_degraded_when_mongo_unreachable():
    failing = MagicMock(side_effect=RuntimeError("connection refused"))
    with patch.object(mongo_module, "ping", failing):
        resp = _call_health()
    assert resp.status_code == 503
    body = json.loads(resp.body)
    assert body == {"status": "degraded", "mongo": "error"}
    # internal error text must not leak into the host-exposed response body
    assert "connection refused" not in resp.body.decode()
