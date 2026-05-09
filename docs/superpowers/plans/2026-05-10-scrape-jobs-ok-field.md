# scrape_jobs ok-field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `ok` boolean to the `scrape_jobs` MCP response so LLM callers can distinguish "0 jobs found (success)" from "site fetch failed (error)", and fix a silent-no-op bug in the `update_config` docstring.

**Architecture:** Two changes to `mcp_server/server.py` — one logic change (add `ok` to return dict) and one docstring fix. Unit tests mock `_load_config`, `run_scraper`, and `_read_site_output` to cover the three distinct response states without hitting the network.

**Tech Stack:** Python 3.12, pytest, unittest.mock

---

## Context: why `ok` is needed

`scrape_jobs` returns `exit_code: 0` even when a fetch fails — the runner writes
`{"error": "fetch failed"}` to disk and returns cleanly. LLM callers reading
`exit_code: 0` + `results[*].sites: []` cannot tell whether the run succeeded
with no matching jobs or failed silently.

Three distinct states:

| State | `ok` | `errors` | `results[*].sites[*].count` |
|-------|------|----------|-----------------------------|
| Fetch succeeded, 0 jobs matched | `true` | `[]` | `0` |
| Fetch succeeded, N jobs matched | `true` | `[]` | `N` |
| Fetch failed (blocked/network) | `false` | `[{reason}]` | — (site absent) |

---

## Files

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `mcp_server/server.py:237` | Add `"ok": len(errors) == 0` to `scrape_jobs` return dict |
| Modify | `mcp_server/server.py:174-196` | Update `scrape_jobs` docstring — document `ok` field semantics |
| Modify | `mcp_server/server.py:117` | Fix `update_config` docstring example (singular `keyword` → list `keywords`) |
| Create | `tests/__init__.py` | Make `tests/` a package |
| Create | `tests/test_scrape_jobs_ok.py` | Unit tests for `ok` field behaviour |
| Modify | `requirements.txt` | Add `pytest>=8.0` |

---

## Task 1: Add pytest to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest**

Append one line to `requirements.txt`:

```
pytest>=8.0
```

- [ ] **Step 2: Install**

```bash
cd /home/orangemango/Documents/workspace/private/test/scrap-test
.venv/bin/pip install pytest>=8.0 -q
```

Expected: resolves without error.

- [ ] **Step 3: Confirm pytest runs**

```bash
.venv/bin/pytest --version
```

Expected output contains `pytest 8.` or later.

---

## Task 2: Write failing tests for `ok` field

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_scrape_jobs_ok.py`

- [ ] **Step 1: Create `tests/__init__.py`**

```python
```

(Empty file — makes `tests/` importable as a package.)

- [ ] **Step 2: Write the tests**

Create `tests/test_scrape_jobs_ok.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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
```

- [ ] **Step 3: Run tests — expect FAIL (KeyError on `ok`)**

```bash
cd /home/orangemango/Documents/workspace/private/test/scrap-test
.venv/bin/pytest tests/test_scrape_jobs_ok.py -v
```

Expected: 4 tests FAIL with `KeyError: 'ok'` or `AssertionError`.

---

## Task 3: Add `ok` field to `scrape_jobs` and fix docstrings

**Files:**
- Modify: `mcp_server/server.py`

- [ ] **Step 1: Add `ok` to the return dict**

In `mcp_server/server.py`, find the `return` statement inside `scrape_jobs` (currently around line 237):

```python
    return {
        "keywords": target_keywords,
        "requested_sites": target_sites,
        "exit_code": exit_code,
        "results": results,
        "errors": errors,
    }
```

Replace with:

```python
    return {
        "ok": len(errors) == 0,
        "keywords": target_keywords,
        "requested_sites": target_sites,
        "exit_code": exit_code,
        "results": results,
        "errors": errors,
    }
```

- [ ] **Step 2: Update `scrape_jobs` docstring**

Replace the `Returns:` block in the `scrape_jobs` docstring. The current block starts with `Returns:` and ends before the closing `"""`. Replace it with:

```python
    Returns:
        dict with keys:
            ok: true when every requested site was reached, regardless of job
                count. Zero jobs with ok=true means the site responded but
                nothing matched your filters or date range — this is normal,
                not an error. ok=false means at least one site failed to fetch.
            keywords: list of keywords actually attempted
            requested_sites: list of site names attempted (per keyword)
            exit_code: scraper exit code (0 = ran without fatal error;
                does NOT reflect per-site fetch success — use ok for that)
            results: list grouped by keyword, each entry:
                {keyword, sites: [{site, fields, count, jobs, ...}]}.
                A site entry is absent from this list when its fetch failed
                (see errors). Each job is projected to the fields configured
                for that site and stamped with `matched_keyword`.
                Canonical fields: site, matched_keyword, title, company, url,
                location, salary, posted_date, posted_at, work_type,
                employment_type, experience_level, job_id.
                Fields a site cannot extract are returned as null.
            errors: list of {keyword, site, reason} for any pair that failed.
                Presence of entries here means ok=false.
```

- [ ] **Step 3: Fix `update_config` docstring example**

Find the `Args:` block in `update_config`. It currently contains:

```python
            {"keyword": "data analyst"}
```

Replace that line with:

```python
            {"keywords": ["data analyst"]}
```

Full corrected `Args:` block should read:

```python
    Args:
        patch: dict to merge in. Examples:
            {"keywords": ["data analyst"]}
            {"max_age_hours": 24}
            {"sites": {"linkedin": {"enabled": false}}}
            {"sites": {"glints": {"max_age_hours": 12}}}
```

Note: `{"keyword": "data analyst"}` (singular) is silently ignored when the
config already has `keywords: [...]` (plural list) because `_resolve_keywords`
always prefers the plural key. The correct single-keyword patch is always
`{"keywords": ["the keyword"]}`.

- [ ] **Step 4: Run tests — expect all PASS**

```bash
cd /home/orangemango/Documents/workspace/private/test/scrap-test
.venv/bin/pytest tests/test_scrape_jobs_ok.py -v
```

Expected:

```
PASSED tests/test_scrape_jobs_ok.py::test_ok_true_when_zero_jobs
PASSED tests/test_scrape_jobs_ok.py::test_ok_true_when_jobs_found
PASSED tests/test_scrape_jobs_ok.py::test_ok_false_when_fetch_failed
PASSED tests/test_scrape_jobs_ok.py::test_ok_false_when_output_missing
4 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/orangemango/Documents/workspace/private/test/scrap-test
git add mcp_server/server.py tests/__init__.py tests/test_scrape_jobs_ok.py requirements.txt
git commit -m "feat(mcp): add ok field to scrape_jobs response to distinguish 0-jobs from fetch error"
```

---

## Self-review

**Spec coverage:**
- `ok: bool` added to response ✓
- `ok` semantics documented in docstring ✓
- `update_config` docstring example fixed ✓
- Tests cover: ok=true/0-jobs, ok=true/N-jobs, ok=false/fetch-error, ok=false/missing-output ✓

**Placeholder scan:** No TBDs. All code blocks complete.

**Type consistency:** `ok` is `bool` throughout (Python `len(errors) == 0` always returns `bool`).
