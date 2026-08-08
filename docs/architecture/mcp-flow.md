# MCP server flow

How `mcp_server/server.py` is reached, what it exposes, and what
`scrape_jobs` actually does end to end. The CronJob bot is only one of its
callers — see [`cronjob-flow.md`](cronjob-flow.md) for that side, which
treats everything below as a single opaque tool call.

Diagrams live beside this file as standalone `.mermaid` sources.

## 1. Topology and tool surface

**Diagram:** [`mcp-topology.mermaid`](mcp-topology.mermaid)

A single-replica `Deployment` runs FastMCP over streamable HTTP on `:8080`,
fronted by the `job-scraper-mcp-service` ClusterIP so in-cluster callers reach
it at `http://job-scraper-mcp-service/mcp`. `/health` is a custom Starlette
route, not a tool: it pings Mongo off the event loop and answers `503
degraded` rather than leaking the error into a host-exposed body.

Every tool delegates to the same `scraper` package the CLI uses — the MCP
layer holds no business logic of its own, so MCP behaviour matches
`python -m scraper` exactly. `update_config` is the only tool that mutates
`config.yaml`, and the bot prompt is explicitly forbidden from calling it.

## 2. `scrape_jobs` end to end

**Diagram:** [`mcp-scrape-jobs.mermaid`](mcp-scrape-jobs.mermaid)

The one call the cron bot makes. The diagram covers everything between the
request and the returned JSON: config load, the fan-out over
`keyword × site` pairs, the per-pair pagination and filtering loop, reading
the output files back, and the status/Mongo writes.

### Notes on the parts that bite

- **`ok` is reachability, not yield.** `ok: true` with zero jobs means every
  site answered but nothing survived the filters — normal, not an error.
  `exit_code` only reports fatal runner failure and does *not* track per-site
  fetch success.
- **A failed site is absent from `results`**, and present in `errors` with an
  `attempts` list of per-fetcher outcomes (`http_403`, `challenge`, `timeout`,
  `runtime_error`, `not_installed`).
- **Dedup is server-side and cross-run.** `SeenStore` means the same posting
  is never returned twice — within a run, or across runs — so callers need no
  dedup of their own. It fails soft: unreachable Mongo means everything looks
  new, favouring a repost over silence.
- **Two output files per pair.** `<site>.raw.json` is everything parsed with
  only the site's own query params applied; `<site>.json` is post-age,
  post-filter, post-limit, post-projection. Both land in the Mongo run
  document (`raw_results` / `filtered_results`); only the filtered set is
  returned to the caller.
- **The run document is inserted here, not by the bot.** `scrape_jobs` returns
  its `mongo_id`, and the bot later patches Discord columns onto that same
  document via `update_scrape_run` — never a second insert.

## Rendering

GitHub does not render bare `.mermaid` files; open them in an IDE with a
mermaid preview, paste into <https://mermaid.live>, or render locally:

```bash
npx -y @mermaid-js/mermaid-cli -i docs/mcp-scrape-jobs.mermaid -o /tmp/mcp.svg
```
