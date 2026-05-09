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

## Step 2 — Format per job

For each job in `results[*].sites[*].jobs`, build a Discord message using
this template (adjust spacing as needed):

```
## {title}
{company} | {location} | {posted_date} | [link]({url})

**Matched**: {matched_keyword} on {site}
{salary if present}
{work_type if present} · {employment_type if present}
```

Skip optional lines (salary, work_type, employment_type) when the value
is null. Anchors (`title`, `company`, `url`) are always present.

If the per-site result has `count: 0`, skip silently (don't post a
"no jobs found" message — too noisy).

## Step 3 — Post each job to Discord

Read the bot token from `/home/node/.claude/channels/discord/.env`.

Send each job as a **separate message** to Discord channel
`1330393101084266609`. One API call per job. Loop through all jobs and
send individually via `node` — export `BOT_TOKEN` and `MSG` as env vars,
never inline:

```sh
export BOT_TOKEN=<token>
export MSG=<formatted message for one job>
node -e "
const https = require('https');
const body = JSON.stringify({content: process.env.MSG});
const req = https.request({
  hostname: 'discord.com',
  path: '/api/v10/channels/1330393101084266609/messages',
  method: 'POST',
  headers: {
    'Authorization': 'Bot ' + process.env.BOT_TOKEN,
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

## Step 4 — Summary footer (optional)

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
- Keep individual messages under 2000 characters (Discord limit). Truncate
  the longest line if needed and append `…`.
