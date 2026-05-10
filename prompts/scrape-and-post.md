# Multi-site job scraper

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
  "errors": [{"keyword": "...", "site": "...", "reason": "..."}]
}
```

If `exit_code != 0` or `errors` is non-empty, include a one-line
diagnostic at the top of the Discord output. Continue and post whatever
jobs DID land — partial output beats silence.

## Step 2 — Pull formatting config

Read these from `/workspace/config.yaml` using `yq` (already in PATH):

```sh
TEMPLATE="$(yq -r '.bot.message_template' /workspace/config.yaml)"
MAX_CHARS="$(yq -r '.bot.max_chars // 1900' /workspace/config.yaml)"
```

`TEMPLATE` carries `{placeholder}` tokens that match canonical Job field
names (e.g. `{title}`, `{company}`, `{location}`, `{posted_date}`,
`{url}`, `{matched_keyword}`, `{site}`, `{salary}`, `{work_type}`,
`{employment_type}`, `{experience_level}`, `{job_id}`, `{posted_at}`,
`{requirements}`).

## Step 3 — Format per job

For each job in `results[*].sites[*].jobs`, substitute every
`{field_name}` placeholder in `TEMPLATE` with the job's value for that
field. If a referenced field is null/missing, drop the line containing
that placeholder rather than emitting a literal `null`. Anchors
(`title`, `company`, `url`) are always present.

If the per-site result has `count: 0`, skip silently (don't post a
"no jobs found" message — too noisy).

If a final formatted message exceeds `MAX_CHARS`, truncate to fit and
append `…` to the truncated line.

## Step 4 — Post each job to Discord

Both the bot token and the channel ID come from the bot container's
environment:

- `DISCORD_BOT_TOKEN` — Discord application bot token (with
  `Send Messages` permission in the target channel)
- `DISCORD_CHANNEL_ID` — destination channel ID

Send each job as a **separate message** to that channel. One API call
per job. Loop through all jobs and post individually via `node` — read
the env vars inside the script, never inline the token:

```sh
export MSG=<formatted message for one job>
node -e "
const https = require('https');
const body = JSON.stringify({content: process.env.MSG});
const req = https.request({
  hostname: 'discord.com',
  path: '/api/v10/channels/' + process.env.DISCORD_CHANNEL_ID + '/messages',
  method: 'POST',
  headers: {
    'Authorization': 'Bot ' + process.env.DISCORD_BOT_TOKEN,
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body)
  }
}, res => {
  let d=''; res.on('data',c=>d+=c);
  res.on('end',()=>{const r=JSON.parse(d); console.log(r.id ? 'sent: '+r.id : 'error: '+JSON.stringify(r));});
});
req.write(body); req.end();
"
```

## Step 5 — Summary footer (optional)

After all individual job messages, send one final summary line:

```
Scraped {total_jobs} jobs across {len(keywords)} keyword(s) and
{len(requested_sites)} site(s). Errors: {len(errors)}.
```

Skip this footer if `total_jobs == 0` (the run produced nothing useful).

## Notes

- Do **not** call `update_config`. This prompt is read-only against the
  scraper's behavior — change config separately when needed.
- Deduplicate within a single run if the same `url` appears under
  multiple keywords (rare but possible). Post each unique URL once.
- The `bot.message_template` and `bot.max_chars` are loaded fresh on
  every run, so an edit + redeploy is enough — no prompt rewrite needed.
