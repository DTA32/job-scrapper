# MCP server

`mcp_server/server.py` exposes the scraper as a Model Context Protocol server
over streamable HTTP (default `0.0.0.0:8080`). External Claude sessions
register it and call its tools to inspect, modify, and run the scraper without
shelling into the container.

This page is the canonical reference for what those tools accept and return.

## Boot

```bash
python -m mcp_server.server          # local
docker compose up -d scraper-mcp     # container (orchestration repo)
```

Environment variables:

| Var               | Default       | Purpose                                 |
|-------------------|---------------|-----------------------------------------|
| `MCP_HOST`        | `0.0.0.0`     | Bind address                            |
| `MCP_PORT`        | `8080`        | Bind port                               |
| `SCRAPER_CONFIG`  | `config.yaml` | Path to YAML config (relative or abs)   |

## Registering from a client Claude session

Add an entry to that container's `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "job-scraper": {
      "type": "http",
      "url": "http://scraper-mcp:8080/mcp"
    }
  }
}
```

Hostname `scraper-mcp` assumes both containers share the same Docker network.
Adjust if running elsewhere.

## Tool catalog

### `list_sites`

Read-only. Inspect resolved config without running anything.

**Args**: none.

**Returns**:

```json
{
  "keywords": ["software engineer", "data analyst"],
  "limit": 2,
  "sites": [
    {
      "name": "jobstreet",
      "enabled": true,
      "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1",
      "sample_url": "https://id.jobstreet.com/id/software-engineer-jobs?daterange=1"
    },
    ...
  ]
}
```

Use this first to confirm what `keywords` and which `sites` are active before
calling `scrape_jobs` or proposing a `update_config` patch.

### `get_config`

Read-only. Returns the parsed `config.yaml` contents.

**Args**: none.

**Returns**: parsed YAML as a dict, identical shape to the file on disk.

```json
{
  "keywords": ["software engineer"],
  "limit": 2,
  "concurrency": 2,
  "max_age_hours": 24,
  "filter": {"location": ["jakarta"]},
  "sites": {...}
}
```

Always call `get_config` before `update_config` to know the current shape so
your patch is minimal.

### `update_config`

Write. Deep-merges a patch into `config.yaml`, validates, writes atomically,
and keeps a timestamped backup.

**Args**:

```json
{ "patch": { ... } }
```

The `patch` is a partial config dict. Nested mappings (like `sites`) are
deep-merged; lists and scalars are replaced entirely. To change just one
site's URL or filter, send only that nested path.

**Returns** (success):

```json
{
  "ok": true,
  "applied": { /* full merged config */ },
  "backup": "config.yaml.bak.1778323689"
}
```

**Returns** (validation failure — file untouched):

```json
{
  "ok": false,
  "error": "validation failed: 'limit' must be >= 1, got -5"
}
```

#### Patch examples

Change keyword:
```json
{"patch": {"keywords": ["data analyst"]}}
```

Tighten recency:
```json
{"patch": {"max_age_hours": 6}}
```

Disable LinkedIn for the next runs:
```json
{"patch": {"sites": {"linkedin": {"enabled": false}}}}
```

Add a new search location to the filter:
```json
{"patch": {"filter": {"location": ["jakarta", "bandung", "surabaya"]}}}
```

Per-site filter override:
```json
{"patch": {"sites": {"glints": {"filter": {"employment_type": "internship"}}}}}
```

Replace LinkedIn URL template (e.g. switch to a different geoId):
```json
{"patch": {"sites": {"linkedin": {"url_template": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&geoId=104884688&f_TPR=r86400&start=0"}}}}
```

#### Validation

Every patch is materialized and run through `scraper.config_loader.load()`
before the live file is replaced. The same rules listed in
[`configuration.md`](configuration.md) apply: malformed `limit`, missing
required keys, invalid URL placeholders, etc. all return `{ok: false, error: …}`.

#### Backup and rollback

A copy of `config.yaml` is saved to `config.yaml.bak.<unix-ts>` immediately
before the new content is written. Backups are gitignored (`config.yaml.bak.*`).
To roll back manually: `mv config.yaml.bak.<ts> config.yaml`.

#### Required permissions

The MCP server's bind mount must be **read-write** for `update_config` to
succeed. Recommended compose for the MCP service:

```yaml
services:
  scraper-mcp:
    volumes:
      - ./config.yaml:/app/config.yaml         # rw — drop ":ro" to allow writes
      - ./output:/app/output                   # rw — runtime output
      - ./docs:/app/docs:ro                    # ro — bundled markdown references
```

If the config mount is read-only, `update_config` returns
`{ok: false, error: "write failed: ..."}`.

The `docs:/app/docs:ro` mount makes the markdown reference docs (this file,
`runbook.md`, `configuration.md`, `sites.md`, etc.) live-readable from inside
the container. Edit any doc on the host and the next read inside the
container sees it — no rebuild needed. Drop the mount for production
deployments where docs aren't expected to change at runtime.

### `scrape_jobs`

Run the scraper. Triggers fetches across `(keyword, site)` pairs and returns
aggregated results.

**Args** (all optional):

```json
{
  "sites": ["linkedin", "indeed"],
  "keywords": ["data analyst"]
}
```

- `sites`: list of site names to scrape. Omitted = all enabled sites.
- `keywords`: list of keywords to scrape. Omitted = all configured keywords.

**Returns**:

```json
{
  "keywords": ["data analyst"],
  "requested_sites": ["linkedin", "indeed"],
  "exit_code": 0,
  "results": [
    {
      "keyword": "data analyst",
      "sites": [
        {
          "site": "linkedin",
          "fields": ["title", "company", "url", ...],
          "max_age_hours": 24,
          "filter": {"location": ["jakarta"]},
          "count": 2,
          "jobs": [...]
        },
        {"site": "indeed", ...}
      ]
    }
  ],
  "errors": [
    {"keyword": "data analyst", "site": "glints", "reason": "fetch failed"}
  ]
}
```

`results` is always grouped by keyword first, then site. `errors` collects
any pair whose JSON couldn't be read or whose fetch failed.

## Operational rules for Claude callers

When asked to change scraper behavior at runtime, follow this loop:

1. Call `get_config` (or `list_sites` for a higher-level view).
2. Construct a minimal `patch` reflecting only the user's request.
3. Call `update_config` with that patch.
4. If `ok=false`, surface the `error` to the user — do NOT retry with a
   different patch unless the user agrees. The error is from the same
   validator the scraper itself uses.
5. On success, optionally call `scrape_jobs` to confirm the new config
   produces expected output.

Avoid:

- Sending a full `config` object as a "replacement" — always patch.
- Inventing keys not in [`configuration.md`](configuration.md).
- Modifying URL templates without checking [`sites.md`](sites.md) for the
  site's expected query-param vocabulary.
- Silently retrying on validation errors.

For specific edit recipes (most common user requests mapped to exact
patches), see [`runbook.md`](runbook.md).
