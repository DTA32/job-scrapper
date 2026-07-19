# Multi-site job scrape

Execute all steps below now, in order. Do not ask for confirmation.

## Step 1 — Run the scraper

Call the `job-scraper` MCP tool `scrape_jobs` with no arguments. It will run
every enabled site for every configured keyword, applying the recency and
content filters from the bound `config.yaml`, and return aggregated results.

The response shape is:

```json
{
  "keywords": ["software engineer", "data analyst"],
  "requested_sites": ["jobstreet", "glints", "linkedin", "indeed"],
  "exit_code": 0,
  "results": [
    {
      "keyword": "software engineer",
      "sites": [
        {"site": "jobstreet", "fields": [...], "count": N, "jobs": [...]},
        ...
      ]
    },
    ...
  ],
  "errors": [{"keyword": "...", "site": "...", "reason": "..."}],
  "mongo_id": "<MongoDB _id of this run's document, or null if Mongo was unreachable>"
}
```

If `exit_code != 0` or `errors` is non-empty, include a one-line
diagnostic at the top of the Discord output. Continue and post whatever
jobs DID land — partial output beats silence.

## Step 2 — Pull formatting config

The message template is a file; the character cap is an environment variable:

```sh
TEMPLATE="$(cat /workspace/scraper-bot/prompts/response_template.md)"
MAX_CHARS="${MAX_CHARS:-1900}"
```

`TEMPLATE` carries `{placeholder}` tokens that match canonical Job field
names (e.g. `{title}`, `{company}`, `{location}`, `{posted_date}`,
`{url}`, `{matched_keyword}`, `{site}`, `{salary}`, `{work_type}`,
`{employment_type}`, `{experience_level}`, `{job_id}`, `{posted_at}`,
`{requirements}`).

## Step 3 — Format per job

For each job in `results[*].sites[*].jobs`, substitute every
`{field_name}` placeholder in `TEMPLATE` with the job's value for that field.

**Null handling.** Drop the *placeholder*, not the whole line. Remove the token
along with any separator left dangling beside it (` | `, a trailing `:`), then
drop the line only if nothing but its label survives. This matters for lines
carrying two fields: `{company} | {location}` must still render the company when
the location is null. Anchors (`title`, `company`, `url`) are always present.

A **section header whose entire body was dropped must drop with it** — if a job
has no requirements, the `**Kualifikasi**` heading goes too, rather than sitting
above nothing.

**Handling `{posted_date}`**: values arrive in mixed shapes — bare dates
(`2026-07-18`) and full ISO-8601 timestamps (`2026-07-16T11:06:12.929Z`,
`2026-07-17T05:00:00+00:00`). Normalize **any** ISO-8601 value to
`Weekday, DD Month YYYY`, with no time of day:

- If it carries a timezone, convert to **UTC+7 (WIB)** before formatting, so the
  date matches the reader's local day.
  e.g. `2026-07-17T22:30:00Z` → `Friday, 18 July 2026`.
- If it is a bare `YYYY-MM-DD`, treat it as already WIB and do not shift it.
- Anything that will not parse passes through unchanged.

**Handling `{requirements}`**: the value is a slice of the raw job description,
already windowed server-side by `requirements_max_chars`. The window is anchored
on the qualifications heading, so the text may begin *and* end mid-document and
is marked with a leading/trailing `…` when it does — that is expected, do not
flag it and do not repeat the `…` in your output.

Emit the block as **its own heading line, then at most 3 bullets**, each at most
80 characters, one per line prefixed with `•`, truncating an over-long item with
`…`. The template supplies no heading — you choose it:

- **Preferred — a real qualifications section.** Extract candidate-facing items:
  things the candidate must have, know, or be. Keep sections like "What We're
  Looking For", "Requirements", "Qualifications", "We Need", "Kualifikasi".
  Strip duties ("What You'll Do", "Responsibilities") and benefits ("Perks").
  Head the block `**Kualifikasi**`.
- **Fallback — no clean qualifications section.** The server-side anchor matches
  the word "requirements" anywhere, so it sometimes lands mid-sentence inside
  the duties text. Do **not** drop the block in that case. Fall back to the
  first 3 substantive lines of the value, skipping company boilerplate ("About
  <Company>", marketing copy). Head the block `**Ringkasan**` so duties are not
  mislabelled as qualifications.
- Drop the block entirely — heading included, per the null rule above — only
  when the value is null or contains nothing but boilerplate.

If the per-site result has `count: 0`, skip silently (don't post a
"no jobs found" message — too noisy).

## Step 4 — Batch jobs into messages, then post to Discord

The destination is a Discord **webhook URL** from the environment:

- `DISCORD_WEBHOOK_URL` — the full webhook URL
  (`https://discord.com/api/webhooks/<id>/<token>`)

**Batching.** Do not send one message per job — a 29-job run produced 30
messages in testing, which reads as spam. Pack multiple jobs per message:

- Group by keyword, and open each message with that keyword as a level-1 header
  (`# software engineer`). Job titles in the template are level-2, so the keyword
  must stay level-1 or the two render at the same weight. A single message never
  mixes keywords.
- Greedily append formatted jobs to the current message while the assembled
  text stays within `MAX_CHARS`. When the next job would push it over, send
  the current message and start a new one, repeating the keyword header.
- **Never split one job across two messages.**
- Separate consecutive jobs inside a message with a `---` line.
- If a single job exceeds `MAX_CHARS` on its own, truncate that job to fit and
  append `…`.

`MAX_CHARS` caps the **assembled message**, not the per-job block. Discord's own
hard limit is 2000, so `MAX_CHARS` must stay at or below that.

**Posting.** One HTTP request per assembled message, via `node` — read the
webhook URL from the environment inside the script, never inline it.
Webhooks are rate-limited (~30 requests/minute): on HTTP 429 read the
`retry_after` value from the JSON body and sleep that many seconds before
retrying that message; otherwise pause briefly (~1s) between posts.

```sh
export MSG=<one assembled message (keyword header + its batched jobs)>
node -e "
const {URL} = require('url');
const https = require('https');
const u = new URL(process.env.DISCORD_WEBHOOK_URL);
const body = JSON.stringify({content: process.env.MSG});
const req = https.request({
  hostname: u.hostname,
  path: u.pathname + u.search,
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body)
  }
}, res => {
  let d=''; res.on('data',c=>d+=c);
  res.on('end',()=>{
    const ok = res.statusCode >= 200 && res.statusCode < 300;
    console.log(ok ? 'sent' : 'error: ' + res.statusCode + ' ' + d);
  });
});
req.write(body); req.end();
"
```

A successful webhook POST returns `204 No Content` (empty body), so key
success off the 2xx status code, not a parsed response id.

## Step 5 — Summary footer (optional)

After all individual job messages, send one final summary line:

```
Scraped {total_jobs} jobs across {len(keywords)} keyword(s) and
{len(requested_sites)} site(s). Errors: {len(errors)}.
```

Skip this footer if `total_jobs == 0` (the run produced nothing useful).

## Step 6 — Record the Discord outcome in MongoDB

`scrape_jobs` already stored this run (raw + filtered results, per-site counts).
Your job here is only to add the Discord columns to that **same** document.

If `mongo_id` from Step 1 is null, skip this step (Mongo was unreachable; job
posting already happened and takes priority).

Otherwise call the `job-scraper` MCP tool `update_scrape_run` with:

```json
{
  "run_id": "<mongo_id from Step 1>",
  "patch": {
    "discord_sent_status": "<'success' if no posts failed, else 'failed'>",
    "run_metadata.bot_post_status": {
      "total_posted": "<number of Discord messages sent successfully>",
      "total_jobs_posted": "<number of jobs carried by those messages>",
      "failed": "<number of messages that errored or got a non-2xx response>"
    }
  }
}
```

Notes:
- Since Step 4 batches, messages and jobs are different counts — report both.
  `total_jobs_posted` is what reconciles against the run's job total;
  `total_posted` and `failed` are message counts.
- `discord_sent_status` is `"success"` when `failed == 0` (including when there
  were no jobs to post), else `"failed"`.
- **Never** put `DISCORD_WEBHOOK_URL` (it embeds a secret token) in the patch.
- The `"run_metadata.bot_post_status"` dot-notation key updates the nested field
  without overwriting the rest of `run_metadata`.
- If `update_scrape_run` returns `{ok: false}`, print one diagnostic line
  (`MongoDB update failed: <error>`) but do **not** retry or abort.

## Notes

- Do **not** call `update_config`. This prompt is read-only against the
  scraper's behavior — change config separately when needed.
- `scrape_jobs` already applies cross-run deduplication server-side: it only
  returns jobs not seen in previous runs, and never the same posting twice
  within a run. Just post everything it returns — no extra dedup needed.
- The message template (`prompts/response_template.md`) and `MAX_CHARS` are read
  fresh on every run, so editing the template file or the env var is enough —
  no prompt rewrite needed.
