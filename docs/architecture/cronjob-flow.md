# CronJob flow

What happens on each scheduled tick, from the Kubernetes `CronJob` down to
the Discord post and the MongoDB patch.

The scrape itself is one MCP tool call and is deliberately drawn as a single
opaque box here — its internals are in [`mcp-flow.md`](mcp-flow.md) /
[`mcp-scrape-jobs.mermaid`](mcp-scrape-jobs.mermaid).

Diagrams live beside this file as standalone `.mermaid` sources.

## 1. Kubernetes topology

**Diagram:** [`cronjob-topology.mermaid`](cronjob-topology.mermaid)

`k8s/cronjob.yaml` fires at **20:00 Asia/Jakarta** daily with
`concurrencyPolicy: Forbid`, so a tick is skipped outright if the previous
run is still going. Each tick creates a Job whose pod overrides the image
`CMD` with `/bin/sh cron/run-scraper.sh`.

The pod takes env from the ConfigMap (`BOT_MODEL`, `TZ`, `MAX_CHARS`, Mongo
db/collection names, the `CLAUDE_CONFIG_*` paths) and the Secret (`MONGO_URI`,
`DISCORD_WEBHOOK_URL` — that's all of it). There are no Anthropic credentials
in either: auth comes solely from `job-scraper-claude-pvc`, mounted at
`/claude-config`, which is where `CLAUDE_CONFIG_DIR` and `CLAUDE_CONFIG_FILE`
point. That PVC is seeded from a `claude login` performed elsewhere, so wiping
it silently breaks every subsequent tick.

`restartPolicy: OnFailure` means a non-zero exit from `run-scraper.sh` gets
the pod retried — worth knowing before you make the script fail hard on a
partial run.

### Why the claude flags look like that

`run-scraper.sh` passes `--mcp-config .mcp.json --strict-mcp-config`
explicitly. The image *does* bake in a project-scoped `.mcp.json`, but
project-scoped servers need a trust approval recorded per project path in
`CLAUDE_CONFIG_FILE` — and that file is seeded from a `claude login` on
another machine, so no approval exists for `/workspace/scraper-bot`. Without
the explicit flags the MCP tools can silently go missing and the run dies at
Step 1 with nothing posted. `--dangerously-skip-permissions` covers the
missing TTY; `--verbose --output-format stream-json` is what makes each step
stream into `cron/scraper.log` live instead of buffering to the end.

## 2. The run itself

**Diagram:** [`cronjob-run.mermaid`](cronjob-run.mermaid)

The six steps of `prompts/scrape-and-post.md`, in order:

| Step | What it does | Where the work lives |
|---|---|---|
| 1 | `scrape_jobs` with no arguments | MCP server — see `mcp-scrape-jobs.mermaid` |
| 2 | Read `prompts/response_template.md` | fresh every run; editing the template needs no prompt rewrite |
| 3 | Substitute `{field}` tokens per job | the model — null placeholders drop, not whole lines |
| 4 | Write `/tmp/jobs-YYYY-MM-DD.md` | the model — `TZ=Asia/Jakarta` makes `date +%F` the WIB date |
| 5 | `node cron/send-digest.js` | code, not the prompt — see diagram 3 |
| 6 | `update_scrape_run` with the Discord columns | MCP server, patching the run doc from step 1 |

Two early exits worth remembering:

- `total_jobs == 0` → steps 4 and 5 are skipped entirely. No file, no post,
  no "nothing found" filler message.
- `mongo_id` is null (Mongo was unreachable during the scrape) → step 6 is
  skipped. Posting already happened and takes priority.

A non-zero `exit_code` or a non-empty `errors` list does **not** stop the
run — a one-line diagnostic gets prepended to the summary and whatever jobs
did land still go out.

## 3. Discord delivery

**Diagram:** [`cronjob-send-digest.mermaid`](cronjob-send-digest.mermaid)

`cron/send-digest.js` owns everything after the digest file exists: byte
accounting, splitting, the multipart upload, rate-limit retries, and the
inline fallback. It lives in code rather than in the prompt because all of it
is arithmetic the model would otherwise do by hand — and because step 6
writes those counts to MongoDB, where a recalled number is a wrong number.

The distinction the split logic turns on: **uploads are capped in bytes,
message content is capped in characters.** The digest is Indonesian text with
emoji, so a character count under-reports what Discord actually weighs.

`mode` in the `RESULT` line is the thing to check after a suspicious run —
`inline` means every upload attempt failed and the jobs went out as plain
messages, which is otherwise invisible after the fact.

## Rendering

GitHub does not render bare `.mermaid` files; open them in an IDE with a
mermaid preview, paste into <https://mermaid.live>, or render locally:

```bash
npx -y @mermaid-js/mermaid-cli -i docs/cronjob-run.mermaid -o /tmp/cron.svg
```
