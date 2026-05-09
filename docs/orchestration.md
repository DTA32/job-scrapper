# Orchestration: cron → Claude → Discord

Long-running container with supercronic fires `claude -p "<prompt>"` on a
schedule. The Claude session calls the `scrape_jobs` MCP tool, formats
the result, and posts each job to Discord using the bot token already
saved by the channel plugin during pairing. No webhooks involved.

This mirrors the legacy `job-scraper` container in
`/home/ubuntu/bots/personal-bots` on the VPS. Same shape, different
prompt and a different MCP backend.

## Architecture

```
┌──────────────────────────────────────┐         ┌──────────────────────┐
│  scraper-bot container               │         │   scraper-mcp        │
│  (long-running, Claude image)        │         │   long-running       │
│                                      │  MCP    │   HTTP :8080         │
│   supercronic ─→ run-scraper.sh      │ ──────► │   reads config.yaml  │
│        │                             │         │   runs scrape        │
│        ▼                             │         │   returns aggregated │
│   claude -p "$(cat prompts/...)"     │ ◄────── │   JSON               │
│        │                             │         └──────────────────────┘
│        │  reads bot token from
│        │  /home/node/.claude/channels/discord/.env
│        │
│        ▼  POST /api/v10/channels/<id>/messages
│   Discord channel
└──────────────────────────────────────┘
```

Both containers share the same Docker network so `http://scraper-mcp:8080`
resolves from `scraper-bot`. Scraper-bot has the user's `.claude` dir
mounted, which is how it gets the Discord bot token saved by the channel
plugin during initial pairing.

## Files in this repo (templates)

| File | Purpose |
|---|---|
| `cron/entrypoint.sh` | downloads supercronic on first boot, exec's it |
| `cron/run-scraper.sh` | runs `claude -p "$(cat prompts/scrape-and-post.md)"` and logs |
| `cron/scraper-crontab` | the schedule (default: `0 1 * * *` — daily at 01:00) |
| `prompts/scrape-and-post.md` | the prompt Claude reads each tick — calls MCP tool, formats, posts |
| `claude/mcp.json.example` | project-level MCP registry template (rename to `.mcp.json` when copying to VPS) |
| `.env.example` | required env vars for VPS deployment |

These are templates, not active services in this repo's `docker-compose.yml`.
The repo only ships `scraper` (CLI) and `scraper-mcp` (MCP server).
The bot container lives in your personal-bots compose on the VPS.

## Deployment to the VPS personal-bots stack

1. **Copy this repo's templates** to `/home/ubuntu/bots/personal-bots/scraper-bot/`:
   ```
   /home/ubuntu/bots/personal-bots/scraper-bot/
   ├── cron/
   │   ├── entrypoint.sh
   │   ├── run-scraper.sh
   │   └── scraper-crontab
   ├── prompts/
   │   └── scrape-and-post.md
   └── .mcp.json                 (rename from this repo's claude/mcp.json.example)
   ```

2. **Run scraper-mcp** somewhere on the same Docker network. Options:
   - Build from this repo on the VPS and add a service to your personal-bots compose
   - Pull a prebuilt image from a registry
   - Run as a separate compose stack (then attach scraper-bot to that
     network with `external: true`)

3. **Add the scraper-bot service** to your personal-bots `docker-compose.yml`,
   mirroring your legacy `job-scraper` block:
   ```yaml
     scraper-bot:
       image: ${CLAUDE_IMAGE}
       container_name: scraper-bot
       restart: unless-stopped
       shm_size: ${SHM_SIZE}
       entrypoint: ["/bin/sh", "/workspace/scraper-bot/cron/entrypoint.sh"]
       depends_on: [scraper-mcp]
       volumes:
         - ${CLAUDE_CONFIG_DIR}:/home/node/.claude
         - ${CLAUDE_CONFIG_FILE}:/home/node/.claude.json
         - ${WORKSPACE_DIR}:/workspace
       healthcheck:
         test: ["CMD", "pgrep", "-f", "supercronic"]
         interval: ${HC_INTERVAL}
         timeout: ${HC_TIMEOUT}
         retries: ${HC_RETRIES}
         start_period: ${HC_START_PERIOD}
   ```

4. **Add scraper-bot's env to `/home/ubuntu/bots/personal-bots/.env`**:
   ```
   CLAUDE_IMAGE=claude-code
   CLAUDE_CONFIG_DIR=/home/ubuntu/.claude
   CLAUDE_CONFIG_FILE=/home/ubuntu/.claude.json
   WORKSPACE_DIR=/home/ubuntu/bots/personal-bots
   SHM_SIZE=2gb
   HC_INTERVAL=30s
   HC_TIMEOUT=10s
   HC_RETRIES=3
   HC_START_PERIOD=60s
   ```

5. **Bring it up**:
   ```bash
   cd /home/ubuntu/bots/personal-bots
   docker compose up -d scraper-mcp scraper-bot
   docker compose logs -f scraper-bot
   ```

## Schedule

Edit `cron/scraper-crontab`:

```
0 */6 * * * /bin/sh /workspace/scraper-bot/cron/run-scraper.sh   # every 6h
0 1 * * *   /bin/sh /workspace/scraper-bot/cron/run-scraper.sh   # daily 01:00 (default)
*/30 * * * * /bin/sh /workspace/scraper-bot/cron/run-scraper.sh  # every 30 min
@every 1h    /bin/sh /workspace/scraper-bot/cron/run-scraper.sh  # supercronic shorthand
```

Restart after editing:

```bash
docker compose restart scraper-bot
```

## Discord posting

The prompt instructs Claude to:

1. Read the bot token from `/home/node/.claude/channels/discord/.env`
   (saved there by `/discord:configure` during pairing)
2. POST each job as a separate message to channel `1330393101084266609`
   (hardcoded in `prompts/scrape-and-post.md` — same channel as your
   legacy LinkedIn scraper)
3. Use Node's `https` module via `node -e` to keep token in env vars,
   never inlined in shell

To change the Discord channel, edit the channel ID in
`prompts/scrape-and-post.md`.

To change the bot, re-pair via `/discord:configure` and restart the bot
container so the new token in `/home/node/.claude/channels/discord/.env`
is picked up.

## How `scraper-mcp` is reached

The scraper-bot container has `claude/.mcp.json` accessible at the
project root inside the workspace. When `claude -p` runs from
`/workspace/scraper-bot/`, it picks up `.mcp.json` and registers the
`job-scraper` MCP server pointing at `http://scraper-mcp:8080/mcp`.

If you'd rather register globally (so all your Claude containers see it),
add the entry to `${CLAUDE_CONFIG_FILE}` (the `.claude.json` you mount).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Container restarts on healthcheck failure | supercronic process not running | Check `cron/scraper.log` for crontab parse errors |
| Cron fires but Claude exits with `mcp not found` | `.mcp.json` not in scope | Verify `claude -p` is run with cwd = workspace dir; or add to global `.claude.json` |
| Claude logs `connection refused: scraper-mcp:8080` | scraper-mcp not running or different network | `docker network inspect <net>` and confirm both containers are on it |
| Discord post fails with 401 | Bot token not saved at `/home/node/.claude/channels/discord/.env` | Re-run `/discord:configure <token>` on the user's host Claude session |
| Discord post fails with 403 | Bot lacks send-messages perm in channel | Re-invite bot with the right OAuth scopes |
| Cron never fires | Bad crontab syntax | `docker exec scraper-bot /workspace/scraper-bot/cron/supercronic -test /workspace/scraper-bot/cron/scraper-crontab` |

## Cost considerations

Each cron tick = one Claude API call. With Sonnet pricing and a
multi-site scrape result, expect ~$0.05–0.20 per tick. At daily cadence
that's ~$1.50–6/month. Tighten the schedule or prompt to control cost.
