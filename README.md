# job-scraper

Scrape job listings from four Indonesian job boards (Jobstreet, Glints,
LinkedIn, Indeed) under a unified canonical schema. Drives output through
configurable recency and content filters, runs in parallel, and exposes
itself as a streamable-HTTP MCP server so external Claude Code sessions
can run scrapes and patch config at runtime.

## Quick start

### Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium    # only needed if Indeed is enabled

python -m scraper                        # all enabled sites, all keywords
python -m scraper jobstreet              # one site
python -m scraper --keyword "data analyst"   # ad-hoc keyword override
```

Results land under `output/<keyword-slug>/<site>.json`.

### Docker

```bash
docker compose up --build         # builds + runs scraper-cli once
ls output/                        # JSONs land here on host
```

The compose file includes an `output-init` service that ensures
bind-mounted `output/` is writable by the container's `pwuser` (uid 1000)
on every run — no manual `chown` needed.

### MCP server

```bash
docker build --target mcp-server -t job-scraper-mcp .
docker run --rm -p 8080:8080 \
  -v "$(pwd)/config.yaml:/app/config.yaml" \
  -v "$(pwd)/output:/app/output" \
  job-scraper-mcp
```

Or extend `docker-compose.yml` to bring it up alongside other services.

Register from a Claude Code container:

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

## What the scraper does

- Cross-product of `keywords × sites` runs through a thread pool capped at
  `concurrency` (default 2)
- Per-site adapters extract a canonical Job schema (title, company,
  location, url, salary, posted_date, posted_at, work_type,
  employment_type, experience_level, job_id, matched_keyword)
- Recency filter (`max_age_hours`) drops stale jobs based on parsed
  `posted_at`; URL templates carry server-side recency params for
  efficiency
- Content filter (`filter:` block) supports OR-within-key + AND-across-keys
  with substring + case-insensitive matching for `location`,
  `employment_type`, `work_type`
- Cloudflare-aware: cloudscraper first, playwright-stealth fallback
  (Indeed always falls back due to PerimeterX)
- Output JSON includes the `fields`, `max_age_hours`, and `filter` that
  produced it, so downstream consumers can reproduce or audit a run

## Configuration

Everything is driven by `config.yaml` at the repo root. Schema reference:
[`docs/configuration.md`](docs/configuration.md).

Live editing without SSH: the MCP server's `update_config` tool deep-merges
a patch, validates against the same loader the scraper uses, atomically
writes, and keeps a timestamped backup. See [`docs/mcp.md`](docs/mcp.md).

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — agent operating rules + doc index
- [`docs/configuration.md`](docs/configuration.md) — every `config.yaml` key
- [`docs/mcp.md`](docs/mcp.md) — MCP tool catalog
- [`docs/runbook.md`](docs/runbook.md) — common config-edit recipes
- [`docs/filters.md`](docs/filters.md) — content filter reference
- [`docs/sites.md`](docs/sites.md) — per-site coverage and quirks
- [`docs/architecture.md`](docs/architecture.md) — package map and request flow
- [`docs/orchestration.md`](docs/orchestration.md) — cron + Claude + Discord automated flow

## Project layout

```
scraper/        # CLI + library — runner, config_loader, sites, fetchers
mcp_server/     # FastMCP HTTP server wrapping the scraper
docs/           # all reference + recipes
config.yaml     # the only thing you edit at runtime
Dockerfile      # multi-target: scraper-cli, mcp-server
docker-compose.yml
```

## License

(unspecified)
