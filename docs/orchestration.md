# Orchestration: cron → digest → Discord

The scheduled bot is a deterministic Node.js pipeline with no model in the
loop. Each tick runs `cron/run-scraper.sh`, which runs `node cron/run-digest.js`:
call the `scrape_jobs` MCP tool, render the result into one markdown digest,
post it to a Discord webhook, and record the delivery on the run's MongoDB
document through `update_scrape_run`. A run costs nothing beyond the scrape
itself.

| Where | Scheduler | Defined in |
|---|---|---|
| Kubernetes (production) | CronJob `job-scraper-bot` runs `run-scraper.sh` directly (`schedule: "0 20 * * *"`, `timeZone: Asia/Jakarta`, `concurrencyPolicy: Forbid`, `restartPolicy: OnFailure`); env from `k8s/configmap.yaml` + the `job-scraper-secret` Secret | `k8s/cronjob.yaml`; image built from `Dockerfile.bot` (`k8s/README.md`) |
| Local one-shot | None: `scripts/run_bot_once.sh` builds `job-scraper-bot:local` from `Dockerfile.bot` and runs its default command once | `scripts/run_bot_once.sh` |

## Architecture

```
┌────────────────────────────────────────────┐         ┌────────────────────────┐
│ bot (node:22-slim, no LLM)                 │         │ scraper-mcp            │
│                                            │   MCP   │ FastMCP HTTP :8080     │
│ k8s CronJob, or run_bot_once.sh locally    │  (HTTP) │                        │
│  └─ run-scraper.sh                         │         │                        │
│      └─ node run-digest.js                 │         │                        │
│          │                                 │         │                        │
│          ├─ 1. scrape_jobs ────────────────┼───────► │ reads config.yaml,     │
│          │  ◄──────────────────────────────┼─────────│ scrapes, inserts the   │
│          │     results + mongo_id          │         │ run doc into MongoDB   │
│          │                                 │         │                        │
│          ├─ 2. format.js + requirements.js │         │                        │
│          │     → jobs-<date>.md            │         │                        │
│          ├─ 3. send-digest.js ──────┐      │         │                        │
│          └─ 4. update_scrape_run ───┼──────┼───────► │ patches that run doc   │
└─────────────────────────────────────┼──────┘         └────────────────────────┘
                                      ▼
                    Discord webhook (DISCORD_WEBHOOK_URL)
```

`scrape_jobs` runs synchronously on the server, so step 1 is a single HTTP
request that stays silent until the scrape ends (see
[How `scraper-mcp` is reached](#how-scraper-mcp-is-reached)).

## Files in this repo

| File | Purpose |
|---|---|
| `cron/run-scraper.sh` | cron entrypoint: runs `node cron/run-digest.js`, tees output to `cron/scraper.log`, logs an `ERROR` line on a non-zero exit, always exits 0 |
| `cron/run-digest.js` | one run end to end: scrape → format → post → record; its header lists every env var |
| `cron/lib/mcp.js` | MCP client: `@modelcontextprotocol/sdk` streamable HTTP over undici, socket timeouts disabled |
| `cron/lib/format.js` | template substitution and null rules, `posted_date` formatting, digest assembly, summary lines |
| `cron/lib/requirements.js` | picks the `**Kualifikasi**` / `**Ringkasan**` bullets from a job's `requirements` outline |
| `cron/send-digest.js` | uploads the digest to the webhook — splitting, retries, inline fallback; also a CLI (`DIGEST_PATH`, `DIGEST_SUMMARY`) |
| `cron/*.test.js`, `cron/lib/*.test.js` | `node --test` suite (see [Tests](#tests)) |
| `cron/test-support/` | fake SDK-built MCP server and localhost webhook stub used by the tests |
| `seeds/requirement_samples.runner.js` | builds MongoDB's `requirement_samples`: real outlines harvested from `scrape_runs`, some labelled by hand, read by the labelled extractor test |
| `cron/entrypoint.sh` | `exec`s supercronic; only the root `Dockerfile`'s legacy `bot` stage (claude-code + supercronic) uses it, and nothing uses that stage |
| `cron/package.json` | runtime deps `@modelcontextprotocol/sdk` and `undici`; Node ≥ 22 |
| `Dockerfile.bot` | the bot image: `node:22-slim` with `cron/` and `prompts/`, no LLM, no supercronic; default command runs `cron/run-scraper.sh` once |
| `scripts/run_bot_once.sh` | local one-shot: builds `job-scraper-bot:local` from `Dockerfile.bot` and runs it once against scraper-mcp on `host.docker.internal:8080` |
| `prompts/response_template.md` | per-job template, read each run |
| `claude/mcp.json.example` | MCP registration for an interactive host `claude` CLI; the bot does not read it |

## Run steps

1. **Scrape.** Connect to `MCP_URL` and call `scrape_jobs` with no arguments —
   every enabled site for every configured keyword. An unreachable server, or a
   `{error}` response (config failed validation), aborts the run.
2. **Nothing new?** Zero jobs means no file and no post; the run is still
   recorded as `discord_sent_status: "skipped"`.
3. **Format.** Every job goes through `prompts/response_template.md`
   (see [Formatting](#formatting)); `{requirements}` becomes the block from
   `cron/lib/requirements.js` (see [Requirements block](#requirements-block)).
4. **Write the digest.** `jobs-<WIB YYYY-MM-DD>.md` in `DIGEST_DIR` (default the
   OS temp dir): one `# <keyword>` section per keyword with jobs. Jobs, and the
   sections themselves, are separated by a blank line, `---`, blank line — the
   only places an oversized digest is ever split.
5. **Post.** `sendDigest()` from `cron/send-digest.js` (see
   [Discord posting](#discord-posting)).
6. **Record.** `update_scrape_run` on the run document (see
   [Recording the run](#recording-the-run)).

`run-digest.js` exits non-zero when the scrape could not run or a Discord
message failed. `run-scraper.sh` logs that and still exits 0, so the CronJob
never retries a run that already marked jobs as seen or posted them.

## Formatting

`cron/lib/format.js` substitutes `{field}` placeholders line by line:

- A missing (null or blank) placeholder is removed together with the ` | `,
  `,` or `:` separator it leaves dangling, so `{company} | {location}` still
  renders the company when location is null.
- A line whose placeholders are all missing is dropped.
- A static section header such as `**Details**` or `### Notes` is dropped when
  its whole body dropped.
- `posted_date` is normalized to `Weekday, DD Month YYYY`. Zoned ISO timestamps
  are converted to WIB (Asia/Jakarta); bare dates and zone-less timestamps are
  taken as WIB and not shifted; unparseable values pass through unchanged.
- Runs of blank lines collapse; a value containing `{field}` is never
  re-expanded.

Template placeholders match canonical Job field names — use any of:
`title`, `company`, `url`, `location`, `salary`, `posted_date`,
`posted_at`, `work_type`, `employment_type`, `experience_level`,
`job_id`, `matched_keyword`, `site`, `requirements`. A field outside the
site's `fields` list is always missing.

The Discord message body carries no jobs, only a summary:

```
⚠️ 1 site/keyword pair(s) failed (scraper exit code 1): glints/data analyst: fetch failed
**Job digest — Thursday, 27 August 2026**

_Scraped 12 jobs across 2 keyword(s) and 4 site(s) (bot v1.2.0). Errors: 1._
```

The `⚠️` line appears only when the scraper exit code is non-zero or `errors`
is non-empty (it lists up to five pairs, then `+N more`). `(bot …)` appears only
when `BOT_VERSION` is set.

## Requirements block

`cron/lib/requirements.js` reads the `requirements` outline the scraper sends
(`## ` headings, `- ` list items, blank lines between paragraphs; see
[`mcp.md`](mcp.md#requirements-format)).

Headings are classified by vocabulary (English and Indonesian, a few French)
as qualifications, responsibilities, benefits, about, apply or info. A
qualifications phrase wins outright ("Requirements & Responsibilities" is
qualifications); otherwise the most specific (longest) phrase wins ("Company
Description" is about, not responsibilities).

The block comes from the first of these that yields any bullets:

| # | Source | Block |
|---|---|---|
| 1 | Qualifications section(s). Listed sections come before prose ones ("We are looking for an engineer who…" above the real list), and pure headings before headings that also name the duties ("Tâches et compétences recherchées") | `**Kualifikasi**`, merged in document order |
| 2 | No qualifications heading, but a list whose items mostly read like requirements: candidate traits up front, years of experience, degrees, "… is a plus". Catches bare lists and requirements pasted under a second duties heading | `**Kualifikasi**` |
| 3 | Prose sentences that state a requirement ("Kandidat harus memiliki gelar S1…", "… menjadi nilai tambah", "PORTFOLIO REQUIRED") — Glints' generated descriptions | `**Kualifikasi**` |
| 4 | Responsibilities: their list before prose about the role | `**Ringkasan**` |
| 5 | Any other non-company text | `**Ringkasan**` |
| – | Only about / benefits / apply / info text | nothing; the `{requirements}` line is dropped |

Steps 2–5 run only when no qualifications heading matched.

Besides `## ` headings it recognizes:

- plain-text headings: colon-terminated intro lines ("Bagi Anda yang tertarik
  adalah syarat dan ketentuan yang diperlukan:"), and lines made only of
  vocabulary words ("Job Requirements")
- inline labels: `Requirements: Go, SQL`
- a paragraph opening like "Kami mencari kandidat…" or "The ideal candidate…",
  read as a headless qualifications section

Items are cleaned — bullet glyphs, numbering and emoji stripped, duplicates
removed, link/email-only lines and calls to action dropped, location and perk
lines ("Lokasi Depo …", "Disediakan Mess") dropped from a Kualifikasi,
company-blurb sentences dropped from a Ringkasan — then truncated at a word
boundary with `…` and rendered as `• item`.

| Env | Default | Effect |
|---|---|---|
| `REQ_MAX_ITEMS` | `5` | bullets per job |
| `REQ_MAX_ITEM_CHARS` | `80` | characters per bullet |

Quality is pinned by real postings in MongoDB's `requirement_samples`
collection. `scrape_jobs` records `run_metadata.requirements_format: "outline-v1"`
on every run, and `seeds/requirement_samples.runner.js harvest` copies those runs'
outlines into the collection: one sample per posting, first-seen date kept, text
refreshed from the newest run. Runs from before the marker hold truncated or
flattened text and are skipped. A sample with an `expected` field —
`{heading, items}`, where each item is how that bullet starts — was labelled by
hand. `lib/requirements.golden.test.js` checks every labelled sample and keeps all
samples within the caps. It needs `MONGO_URI` and is skipped without it, so CI
gates on the synthetic `lib/requirements.test.js` only. When a posting renders
badly, label its sample first, then change the rules until the test passes.

```bash
MONGO_URI=... node seeds/requirement_samples.runner.js harvest [--dry-run]
MONGO_URI=... node seeds/requirement_samples.runner.js import <scraper output_dir> [--labels <file>] [--dry-run]
cd cron && MONGO_URI=... npm run test:samples
```

Label a sample in mongosh. A labelled sample keeps the text it was labelled
against: later harvests and unlabelled imports never rewrite it.

```js
db.requirement_samples.updateOne({ _id: "<id>" }, { $set: {
  expected: { heading: "Kualifikasi", items: ["Minimal S1", "Pengalaman 2 tahun"] },
  labelled_at: new Date().toISOString() } })
```

## Bot config and env

| Setting | When it's read | Effect |
|---|---|---|
| `bot.schedule` (`config.yaml`) | Not read | Informational only. The CronJob's `schedule` in `k8s/cronjob.yaml` is the source of truth |
| `prompts/response_template.md` | Each run | Format applied to every job. Baked into the image, so edits ship with a rebuild |
| `DISCORD_WEBHOOK_URL` | Each run | **Required.** Webhook the digest posts to |
| `MCP_URL` | Each run | MCP endpoint. Default `http://job-scraper-mcp-service/mcp` (also set in `k8s/configmap.yaml`); `scripts/run_bot_once.sh` defaults it to `http://host.docker.internal:8080/mcp` |
| `SCRAPE_TIMEOUT_MS` | Each run | Cap on the `scrape_jobs` call; default `1800000` (30 min) |
| `TEMPLATE_PATH` | Each run | Template override; default `prompts/response_template.md` |
| `DIGEST_DIR` | Each run | Where `jobs-<date>.md` is written; default the OS temp dir |
| `BOT_VERSION` | Each run | Optional; shown as `(bot <version>)` in the summary line |
| `REQ_MAX_ITEMS` / `REQ_MAX_ITEM_CHARS` | Each run | Requirements bullets per job / characters per bullet; default `5` / `80` |
| `MAX_FILE_BYTES` | Each run, by `cron/send-digest.js` | Upload cap before the digest splits; default 10 MiB |
| `MAX_CHARS` | Each run, by `cron/send-digest.js` | Per-message cap for the **inline fallback only** — the normal attachment path has no character budget; default `1900` |
| `TZ` | Container start | Clock `run-scraper.sh` log timestamps use; `Asia/Jakarta` in `k8s/configmap.yaml` and by default in `run_bot_once.sh`. The CronJob's schedule follows its own `timeZone`, not `TZ`. Digest dates are always WIB |

On Kubernetes these come from `k8s/configmap.yaml` (`MCP_URL`,
`SCRAPE_TIMEOUT_MS`, `TZ`, `MAX_CHARS`, `REQ_MAX_ITEMS`, `REQ_MAX_ITEM_CHARS`)
and the `job-scraper-secret` Secret (`DISCORD_WEBHOOK_URL`); an edited ConfigMap
applies from the next run. Locally, `scripts/run_bot_once.sh` sources `.env`
(values there override your shell) and passes only `DISCORD_WEBHOOK_URL`,
`MCP_URL`, `TZ` and, when set, `SCRAPE_TIMEOUT_MS`, `MAX_CHARS`,
`MAX_FILE_BYTES`, `REQ_MAX_ITEMS`, `REQ_MAX_ITEM_CHARS` and `BOT_VERSION` into
the container — add any other variable to the script's `docker run`.

Schedule examples (`schedule` in `k8s/cronjob.yaml`, standard five-field cron):

```yaml
schedule: "0 20 * * *"       # daily 20:00 (current; timeZone: Asia/Jakarta)
schedule: "0 */6 * * *"      # every 6h
schedule: "*/30 * * * *"     # every 30 min
```

Kubernetes evaluates the schedule in the CronJob's `timeZone`, not the
container's `TZ`. A changed schedule applies once the manifest is re-applied
(see `k8s/README.md`); `config.yaml`'s `bot.schedule` changes nothing.

Template and code changes ship with the image: rebuild it from `Dockerfile.bot`,
push it, and point the CronJob's `image` at the new tag (see `k8s/README.md`).

## Discord posting

The run's jobs are delivered as **one markdown attachment**, not as a stream of
messages. `run-digest.js` writes the digest file and hands its path and the
summary to `sendDigest()` in `cron/send-digest.js`, which owns everything after
that:

| Concern | Behaviour |
|---|---|
| Transport | One `multipart/form-data` POST to `DISCORD_WEBHOOK_URL` — `payload_json` (the summary) + `files[0]` (the digest) |
| Size | Measures **bytes**, not chars. Over `MAX_FILE_BYTES` (default 10 MiB) the digest splits at job boundaries into `…partNofM.md`, one message each — the cap applies per request, so parts can't share a POST |
| Rate limits | HTTP 429 → sleep `retry_after` from the body; 5xx or a network error → wait 2s; up to 3 attempts per request; ~1s between messages |
| Fallback | A part that still fails is chunked into `MAX_CHARS` plain `content` messages, the summary riding on the first |
| Reporting | Returns `{mode, messages_sent, parts, bytes, failed}`, logged as `RESULT {…}`; `run-digest.js` copies those numbers into the MongoDB run document, including `delivery_mode` so a degraded run is visible afterwards |

A file upload answers **200 with a message object**, unlike a plain content POST
which answers `204 No Content` — the script keys success off any 2xx.

Tradeoff worth knowing: Discord does not render an attached `.md` as rich
markdown. It shows a file card with a text preview, and links only become
clickable once the file is opened. That is the price of collapsing a dozen
messages into one.

`send-digest.js` still runs standalone for ad-hoc sends (the manage TUI's
Discord smoke test uses it):

```bash
DISCORD_WEBHOOK_URL=... DIGEST_PATH=/tmp/digest.md DIGEST_SUMMARY='test' node cron/send-digest.js
```

To change the destination, update `DISCORD_WEBHOOK_URL` in the Secret
(`k8s/secret.yaml`, then re-apply it) or your `.env`; the next run uses it.

## Recording the run

`scrape_jobs` inserts one MongoDB document per run and returns its id as
`mongo_id`. After posting, `run-digest.js` calls `update_scrape_run` with
`run_id: mongo_id` and this patch:

```json
{
  "discord_sent_status": "success",
  "run_metadata.bot_post_status": {
    "total_posted": 1,
    "total_jobs_posted": 12,
    "failed": 0,
    "delivery_mode": "attachment"
  }
}
```

- `discord_sent_status`: `success`, `failed` (a Discord message failed) or
  `skipped` (no jobs, nothing posted)
- `total_posted` counts Discord messages; `delivery_mode` is `attachment`,
  `mixed`, `inline` or `none`
- `mongo_id` null (Mongo unreachable during the scrape) → no update, logged
- A failed update is logged as `MongoDB update failed: …` and never fails the
  run — posting already happened
- The webhook URL is never sent to Mongo: it embeds a secret token

## How `scraper-mcp` is reached

The bot connects to `MCP_URL`:

| Deployment | `MCP_URL` | How it resolves |
|---|---|---|
| Kubernetes | `http://job-scraper-mcp-service/mcp` (`k8s/configmap.yaml`; also the code default) | ClusterIP Service in front of the `job-scraper-mcp` Deployment |
| Local (`scripts/run_bot_once.sh`) | `http://host.docker.internal:8080/mcp` (script default; override in `.env`) | `--add-host=host.docker.internal:host-gateway` maps the name to the host (needed on Linux), where the compose `mcp` profile publishes scraper-mcp on `:8080` |

FastMCP runs the sync `scrape_jobs` tool on its event loop, so the server sends
no bytes — not even headers — until the scrape ends. Node's built-in fetch
abandons a response after 300 s of that, which would cut off any scrape longer
than five minutes. `cron/lib/mcp.js` therefore sends requests through an undici
dispatcher with header and body timeouts disabled, leaving `SCRAPE_TIMEOUT_MS`
as the single cap. `update_scrape_run` gets its own 30 s timeout.

## Tests

```bash
cd cron && npm ci && npm test
```

`node --test` runs `lib/format.test.js` (template rules, dates, summary),
`lib/requirements.test.js` (the extractor's rules), `lib/requirements.golden.test.js`
(the labelled postings in MongoDB; skipped without `MONGO_URI`), `lib/mcp.test.js` (the client
against a real SDK-built MCP server that, like FastMCP, answers only when the
tool returns), `run-digest.test.js` (a whole run against a fake MCP server and a
localhost webhook) and `send-digest.test.js`. Python tests stay under `pytest`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `[digest] run failed: DISCORD_WEBHOOK_URL is not set` | Env missing | Set it in `.env` or the `job-scraper-secret` Secret |
| `[digest] run failed: cannot reach MCP server at <url>: …` | scraper-mcp down or wrong `MCP_URL` | `curl http://localhost:8080/health` on the host (k8s: `kubectl get endpoints job-scraper-mcp-service`); check `MCP_URL` in `k8s/configmap.yaml` or your `.env` |
| `[digest] run failed: MCP error -32001: Request timed out` | Scrape ran longer than `SCRAPE_TIMEOUT_MS` | Raise `SCRAPE_TIMEOUT_MS`, or cut keywords, sites or `max_pages`. The server-side scrape may still finish and mark its jobs seen, so a re-run won't post them |
| `[digest] run failed: scrape_jobs: <reason>` | `scrape_jobs` returned `{error}`: `config.yaml` failed validation | Fix the config (rules in [`configuration.md`](configuration.md)) |
| `[digest] run failed: scrape_jobs failed: …` | The tool raised on the server | `docker logs job-scraper-mcp` / `kubectl logs deploy/job-scraper-mcp` |
| `[digest] no new jobs; nothing to post` | Every match was already seen, or filters and recency admit nothing | Expected when nothing is new; loosen `filter` / `max_age_hours` if it persists |
| `[digest] mongo_id is null (…); run not recorded` | Mongo unreachable when `scrape_jobs` ran | Check Mongo and `MONGO_URI` on scraper-mcp; the digest still posted |
| `MongoDB update failed: …` | Mongo unreachable, or no run document with that id | Same; delivery is unaffected |
| `ERROR: digest run exited with code 1` in the run's output | One of the failures above, or a Discord message failed | Read the lines above it (`kubectl logs job/<name>`, or your terminal for a local run) |
| Digest upload fails with 401/404 | Webhook deleted or `DISCORD_WEBHOOK_URL` wrong/truncated | Re-create the webhook in channel settings, update the Secret or `.env`; the next run uses it |
| Digest upload fails with 413 | File over the guild's upload cap | Lower `MAX_FILE_BYTES` to match the guild's tier so the digest splits sooner |
| Jobs arrive as plain messages, `delivery_mode: "inline"` | Every upload attempt failed; the fallback carried the run | Check the `upload of … failed:` lines in the run's output for the status code |
