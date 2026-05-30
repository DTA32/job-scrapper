# MongoDB Scrape History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every scraping run (raw results, metadata, per-site counts, bot post status) into a MongoDB collection, and expose insert + read operations as MCP tools so the bot can record and query run history.

**Architecture:** A new `mcp_server/mongo.py` module owns all MongoDB I/O with a lazy connection (connects only on first tool call). Two new MCP tools (`insert_scrape_run`, `get_latest_scrape_run`) delegate to it. The `prompts/scrape-and-post.md` prompt gains a final Step 6 that calls `insert_scrape_run` after posting jobs. MongoDB runs as a Docker service on the same default Compose network as `scraper-mcp`, reachable via DNS name `mongo`.

**Tech Stack:** Python 3.12, pymongo ≥ 4.0, MongoDB 7 (Docker), unittest.mock (tests — no real DB needed)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Add `pymongo>=4.0` |
| `docker-compose.yml` | Modify | Add `mongo` service + `MONGO_URI` env to `scraper-mcp` + named volume |
| `mcp_server/mongo.py` | Create | Lazy client, `insert_run`, `get_latest_run` |
| `mcp_server/server.py` | Modify | Import `mongo` module; add `insert_scrape_run` and `get_latest_scrape_run` tools |
| `prompts/scrape-and-post.md` | Modify | Add Step 6: record run via `insert_scrape_run` |
| `tests/test_mongo.py` | Create | Unit tests for `mongo.py` helpers |
| `tests/test_mongo_tools.py` | Create | Unit tests for the two new MCP tools |

---

## Task 1: Add pymongo dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add pymongo to requirements.txt**

Open `requirements.txt` and add this line after `pyyaml`:

```
pymongo>=4.0
```

Full file after edit:
```
cloudscraper>=1.2.71
curl_cffi>=0.7.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
playwright==1.59.0
playwright-stealth>=1.0.6
pyyaml>=6.0
pymongo>=4.0
mcp[cli]>=1.2.0
dateparser>=1.2.0
pytest>=8.0
```

- [ ] **Step 2: Verify pymongo installs**

```bash
pip install pymongo>=4.0
python -c "import pymongo; print(pymongo.version)"
```

Expected output: a version string like `4.x.x`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pymongo dependency"
```

---

## Task 2: Add MongoDB service to docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add `mongo` service and named volume**

The final `docker-compose.yml` should look like this (full file shown — only changes are the `mongo` service, the `MONGO_URI` env on `scraper-mcp`, the `depends_on` mongo entry, and the top-level `volumes` block):

```yaml
services:
  # SERVICE: output-init — fixes output dir ownership before scraper runs (Playwright image runs as root)
  output-init:
    image: mcr.microsoft.com/playwright/python:v1.59.0-jammy
    container_name: job-scraper-init
    user: "0:0"
    entrypoint: ["sh", "-c", "chown -R 1000:1000 /out"]
    restart: "no"
    volumes:
      - ./output:/out

  # SERVICE: scraper — one-shot CLI scraper; network_mode:host for SOCKS5 proxy passthrough
  scraper:
    build:
      context: .
      dockerfile: Dockerfile
      target: scraper-cli
    image: job-scraper:latest
    container_name: job-scraper
    restart: "no"
    profiles: ["scraper"]
    network_mode: host
    depends_on:
      output-init:
        condition: service_completed_successfully
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./output:/app/output
    environment:
      - PROXY_URL=${PROXY_URL:-}

  # SERVICE: mongo — persistent MongoDB store for scrape run history
  mongo:
    image: mongo:7
    container_name: job-scraper-mongo
    restart: unless-stopped
    profiles: ["mcp"]
    ports:
      - "27017:27017"
    volumes:
      - mongo-data:/data/db

  # SERVICE: scraper-mcp — long-running MCP HTTP server; profile-gated so `docker compose up` skips it by default
  scraper-mcp:
    build:
      context: .
      dockerfile: Dockerfile
      target: mcp-server
    image: job-scraper-mcp:latest
    container_name: job-scraper-mcp
    restart: unless-stopped
    profiles: ["mcp"]
    depends_on:
      output-init:
        condition: service_completed_successfully
      mongo:
        condition: service_started
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./output:/app/output
      - ./docs:/app/docs:ro
    environment:
      - MONGO_URI=mongodb://mongo:27017

  # SERVICE: bot — cron bot; runs claude-code on a schedule; profile-gated so `docker compose up` skips it by default
  bot:
    build:
      context: .
      dockerfile: Dockerfile
      target: bot
    image: job-scraper-bot:latest
    container_name: job-scraper-bot
    restart: unless-stopped
    profiles: ["bot"]
    extra_hosts:
      - "host.docker.internal:host-gateway" # allows bot to reach scraper-mcp via host.docker.internal:8080 (Linux only)
    depends_on:
      output-init:
        condition: service_completed_successfully
    environment:
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
      - DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}
    volumes:
      - ~/.claude:/home/node/.claude
      - ~/.claude.json:/home/node/.claude.json
      - ./config.yaml:/workspace/config.yaml:ro
      - ./output:/workspace/output

volumes:
  mongo-data:
```

- [ ] **Step 2: Verify compose config is valid**

```bash
docker compose config --quiet
```

Expected: no output (exit code 0). Any error means the YAML is malformed — fix it before continuing.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add MongoDB service and MONGO_URI to scraper-mcp"
```

---

## Task 3: Write failing tests for mongo.py

**Files:**
- Create: `tests/test_mongo.py`

Write the tests first, before creating `mcp_server/mongo.py`. They must fail at this point.

- [ ] **Step 1: Create `tests/test_mongo.py`**

```python
# tests/test_mongo.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import mcp_server.mongo as mongo_module


def _make_mock_collection() -> MagicMock:
    col = MagicMock()
    col.insert_one.return_value.inserted_id = "507f1f77bcf86cd799439011"
    return col


def test_insert_run_returns_inserted_id():
    mock_col = _make_mock_collection()
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        result = mongo_module.insert_run({"foo": "bar"})
    assert result == "507f1f77bcf86cd799439011"


def test_insert_run_injects_created_at():
    mock_col = _make_mock_collection()
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.insert_run({"run_metadata": {"ok": True}})
    doc = mock_col.insert_one.call_args[0][0]
    assert "_created_at" in doc
    assert "T" in doc["_created_at"]  # ISO-8601 format contains T


def test_insert_run_does_not_mutate_input():
    mock_col = _make_mock_collection()
    original = {"foo": "bar"}
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.insert_run(original)
    assert "_created_at" not in original  # input dict must not be mutated


def test_get_latest_run_returns_none_when_empty():
    mock_col = MagicMock()
    mock_col.find_one.return_value = None
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        result = mongo_module.get_latest_run()
    assert result is None


def test_get_latest_run_sorts_by_created_at_descending():
    mock_col = MagicMock()
    mock_col.find_one.return_value = None
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.get_latest_run()
    mock_col.find_one.assert_called_once_with(sort=[("_created_at", -1)])


def test_get_latest_run_converts_object_id_to_string():
    from bson import ObjectId

    oid = ObjectId("507f1f77bcf86cd799439011")
    mock_col = MagicMock()
    mock_col.find_one.return_value = {
        "_id": oid,
        "foo": "bar",
        "_created_at": "2026-05-28T00:00:00+00:00",
    }
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        result = mongo_module.get_latest_run()
    assert result is not None
    assert result["_id"] == "507f1f77bcf86cd799439011"
    assert result["foo"] == "bar"
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_mongo.py -v
```

Expected: `ModuleNotFoundError: No module named 'mcp_server.mongo'` (or similar import error). If they pass, the module already exists with correct behavior — skip Task 4.

---

## Task 4: Implement mcp_server/mongo.py

**Files:**
- Create: `mcp_server/mongo.py`

- [ ] **Step 1: Create `mcp_server/mongo.py`**

```python
# mcp_server/mongo.py
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
_DB_NAME = "job_scraper"
_COLLECTION_NAME = "scrape_runs"

_client: Any = None


def get_collection() -> Any:
    global _client
    if _client is None:
        from pymongo import MongoClient  # deferred so import cost is zero when unused

        _client = MongoClient(MONGO_URI)
    return _client[_DB_NAME][_COLLECTION_NAME]


def insert_run(data: dict[str, Any]) -> str:
    """Insert a scrape run document. Returns the inserted _id as a string."""
    collection = get_collection()
    doc = {**data, "_created_at": datetime.now(UTC).isoformat()}
    result = collection.insert_one(doc)
    return str(result.inserted_id)


def get_latest_run() -> dict[str, Any] | None:
    """Return the most recent scrape run document, or None if none exist."""
    collection = get_collection()
    doc = collection.find_one(sort=[("_created_at", -1)])
    if doc is None:
        return None
    return {**doc, "_id": str(doc["_id"])}
```

- [ ] **Step 2: Run tests — confirm they pass**

```bash
pytest tests/test_mongo.py -v
```

Expected:
```
PASSED tests/test_mongo.py::test_insert_run_returns_inserted_id
PASSED tests/test_mongo.py::test_insert_run_injects_created_at
PASSED tests/test_mongo.py::test_insert_run_does_not_mutate_input
PASSED tests/test_mongo.py::test_get_latest_run_returns_none_when_empty
PASSED tests/test_mongo.py::test_get_latest_run_sorts_by_created_at_descending
PASSED tests/test_mongo.py::test_get_latest_run_converts_object_id_to_string
```

- [ ] **Step 3: Commit**

```bash
git add mcp_server/mongo.py tests/test_mongo.py
git commit -m "feat: add MongoDB helpers for scrape run persistence"
```

---

## Task 5: Write failing tests for new MCP tools

**Files:**
- Create: `tests/test_mongo_tools.py`

- [ ] **Step 1: Create `tests/test_mongo_tools.py`**

```python
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
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_mongo_tools.py -v
```

Expected: `ImportError: cannot import name 'get_latest_scrape_run' from 'mcp_server.server'` (tools not yet defined). If they pass, the tools already exist — skip Task 6.

---

## Task 6: Add MCP tools to server.py

**Files:**
- Modify: `mcp_server/server.py`

- [ ] **Step 1: Add `from mcp_server import mongo` import to server.py**

In `mcp_server/server.py`, find the block of `from scraper.*` imports at the top and add the mongo import after them:

```python
from scraper.config import ACCEPT_LANGUAGE, USER_AGENT
from scraper.config_loader import AppConfig, ConfigError, keyword_slug, load
from scraper.log import get_logger as _get_logger
from scraper.runner import run as run_scraper
from scraper.types import JOB_FIELD_ORDER
from mcp_server import mongo
```

- [ ] **Step 2: Add `insert_scrape_run` tool — append to server.py after `get_scrape_status`**

Add the following two tools after the `get_scrape_status` function definition (before `test_proxy_connection`):

```python
@mcp.tool()
def insert_scrape_run(run_data: dict[str, Any]) -> dict[str, Any]:
    """Insert a scraping run record into MongoDB for history tracking.

    Args:
        run_data: Arbitrary dict with run details. Recommended keys:
            run_metadata: {ok, exit_code, keywords, requested_sites, errors}
            per_site_counts: {<site>: {<keyword>: <count>}}
            raw_results: full results array from scrape_jobs
            bot_post_status: {total_posted, failed}

    Returns:
        On success: {ok: true, inserted_id: <str>}
        On failure: {ok: false, error: <str>}
    """
    try:
        inserted_id = mongo.insert_run(run_data)
        return {"ok": True, "inserted_id": inserted_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_latest_scrape_run() -> dict[str, Any]:
    """Return the most recent scraping run record from MongoDB.

    Returns:
        {available: false, message: str} when no runs have been recorded
        {available: false, error: str} when MongoDB is unreachable
        {available: true, _id, _created_at, run_metadata, per_site_counts,
         raw_results, bot_post_status, ...} on success
    """
    try:
        doc = mongo.get_latest_run()
        if doc is None:
            return {"available": False, "message": "No scrape runs recorded yet."}
        return {"available": True, **doc}
    except Exception as exc:
        return {"available": False, "error": str(exc)}
```

- [ ] **Step 3: Run all tests — confirm new tools pass and nothing is broken**

```bash
pytest tests/test_mongo_tools.py tests/test_mongo.py tests/test_status.py -v
```

Expected: all green. If `test_status.py` or other tests break, the import of `mongo` at module level is likely causing a side effect — move the import inside each tool function body as `from mcp_server import mongo` and re-run.

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass. Fix any failures before continuing.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py tests/test_mongo_tools.py
git commit -m "feat: add insert_scrape_run and get_latest_scrape_run MCP tools"
```

---

## Task 7: Update prompts/scrape-and-post.md with Step 6

**Files:**
- Modify: `prompts/scrape-and-post.md`

- [ ] **Step 1: Append Step 6 to the prompt file**

Add the following section at the end of `prompts/scrape-and-post.md`, before the `## Notes` section (so Notes stays last):

```markdown
## Step 6 — Record the run in MongoDB

After sending the summary footer (or immediately after posting all job messages if
`total_jobs == 0`), call the `job-scraper` MCP tool `insert_scrape_run` with a
single `run_data` argument assembled as follows:

```json
{
  "run_metadata": {
    "ok": <bool — top-level ok from scrape_jobs>,
    "exit_code": <int>,
    "keywords": ["..."],
    "requested_sites": ["..."],
    "errors": [...]
  },
  "per_site_counts": {
    "<site_name>": { "<keyword>": <count_int> }
  },
  "raw_results": <the full results array from scrape_jobs>,
  "bot_post_status": {
    "total_posted": <number of Discord messages sent successfully>,
    "failed": <number that errored or got a non-2xx response>
  }
}
```

`per_site_counts` is derived from `results[*].sites[*]`:

```js
// pseudocode
for each keyword_group in results:
  for each site_entry in keyword_group.sites:
    per_site_counts[site_entry.site][keyword_group.keyword] = site_entry.count
```

If `insert_scrape_run` returns `{ok: false}`, print one diagnostic line
(`MongoDB insert failed: <error>`) but do **not** retry or abort — job posting
always takes priority over history recording.
```

- [ ] **Step 2: Verify the file structure is intact**

```bash
grep -n "^## Step" prompts/scrape-and-post.md
```

Expected output:
```
3:## Step 1 — Run the scraper
35:## Step 2 — Pull formatting config
49:## Step 3 — Format per job
74:## Step 4 — Post each job to Discord
109:## Step 5 — Summary footer (optional)
<line>:## Step 6 — Record the run in MongoDB
```

All 6 steps must be present with correct headings.

- [ ] **Step 3: Commit**

```bash
git add prompts/scrape-and-post.md
git commit -m "feat: record scrape run history in MongoDB after bot posts"
```

---

## Task 8: Smoke test end-to-end (optional but recommended)

This task verifies the Docker stack works with MongoDB before declaring done.

- [ ] **Step 1: Build and start the mcp profile**

```bash
docker compose --profile mcp up --build -d
```

Expected: three containers start — `job-scraper-init` (exits 0), `job-scraper-mongo`, `job-scraper-mcp`.

- [ ] **Step 2: Verify MongoDB is reachable from scraper-mcp container**

```bash
docker exec job-scraper-mcp python -c "
import os
from pymongo import MongoClient
uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
c = MongoClient(uri, serverSelectionTimeoutMS=3000)
c.admin.command('ping')
print('mongo ok')
"
```

Expected output: `mongo ok`

- [ ] **Step 3: Call insert_scrape_run via MCP HTTP**

```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"insert_scrape_run","arguments":{"run_data":{"test":true}}}}'
```

Expected: response JSON containing `"ok": true` and `"inserted_id"`.

- [ ] **Step 4: Call get_latest_scrape_run**

```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_latest_scrape_run","arguments":{}}}'
```

Expected: response JSON with `"available": true` and `"test": true` in the result.

- [ ] **Step 5: Tear down**

```bash
docker compose --profile mcp down
```

---

## Self-Review Checklist

- [x] **pymongo added** — Task 1
- [x] **Mongo Docker service** — Task 2, under `mcp` profile, same network as `scraper-mcp`
- [x] **`MONGO_URI` env in `scraper-mcp`** — Task 2, `mongodb://mongo:27017`
- [x] **`mongo.py` helpers** — Task 4: `insert_run` (immutable, injects timestamp), `get_latest_run` (ObjectId → str)
- [x] **MCP tools** — Task 6: `insert_scrape_run`, `get_latest_scrape_run`
- [x] **Error handling** — both tools catch all exceptions, return `{ok: false}` / `{available: false}` without raising
- [x] **Prompt Step 6** — Task 7: inserts after summary, non-blocking on failure
- [x] **Tests** — Tasks 3 and 5 written before implementation (TDD); no real MongoDB needed
- [x] **Immutability** — `insert_run` builds `{**data, "_created_at": ...}` rather than mutating input; `get_latest_run` returns `{**doc, "_id": ...}` rather than mutating the mongo doc
- [x] **No placeholder steps** — all steps contain actual code
