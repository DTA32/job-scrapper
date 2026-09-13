# Deploy pipeline

GitHub Actions builds **two** Docker images, pushes both to GitHub
Container Registry, and SSHs into the VPS to (re)create both
containers via `docker run`.

Trigger: push to `main` (or manual via "Run workflow" in the Actions tab).

**Fully isolated**: nothing on the VPS host beyond docker itself. No
mounted files, no state directories, no manual config. Each deploy
starts both containers fresh from new images. Configuration baked into
images at build time; secrets injected via `docker run -e`.

## What ships

| Image | Container | Role |
|---|---|---|
| `ghcr.io/<owner>/<repo>:mcp-<sha>` | `scraper-mcp` | FastMCP HTTP server on port 8080 |
| `ghcr.io/<owner>/<repo>:bot-<sha>` | `scraper-bot` | supercronic + Node.js digest pipeline (`cron/run-digest.js`); scrapes via MCP on schedule and posts to Discord |

Both also tagged as `:mcp-latest` / `:bot-latest`.

## What the pipeline does

1. **build-mcp** — build `mcp-server` Dockerfile target → push
2. **build-bot** — build `bot` Dockerfile target → push (parallel with build-mcp)
3. **deploy-mcp** — SSH, `docker pull` + replace `scraper-mcp` container
4. **deploy-bot** — SSH, `docker pull` + replace `scraper-bot` container with secrets injected

deploy-bot runs after deploy-mcp so the MCP server is up before the bot
starts cron-firing.

## Required GitHub secrets

Repo → Settings → Secrets and variables → Actions → **Secrets** tab.

| Secret | Used by | Value |
|---|---|---|
| `SSH_HOST` | both deploy jobs | `43.157.226.237` |
| `SSH_USER` | both deploy jobs | `ubuntu` |
| `SSH_PRIVATE_KEY` | both deploy jobs | private key for VPS SSH |
| `DISCORD_BOT_TOKEN` | deploy-bot | Discord application bot token (with Send Messages perm in target channel) |
| `DISCORD_CHANNEL_ID` | deploy-bot | Discord channel ID where job posts go |

`GITHUB_TOKEN` is auto-provided — used to push to ghcr.io.

## GitHub variables

None are required. Same UI, **Variables** tab (plain text, visible in
logs): the workflow reads `MONGO_ROOT_USER`, `MONGO_DB_NAME` and
`MONGO_COLLECTION_NAME` in deploy-mcp and `TZ` in deploy-bot, each with a
default. The bot needs no model credentials and no host mounts.

## Hardcoded values (workflow env block)

| Var               | Default       | Purpose                          |
|-------------------|---------------|----------------------------------|
| MCP `CONTAINER_NAME` | `scraper-mcp` | Name of the MCP container     |
| Bot `CONTAINER_NAME` | `scraper-bot` | Name of the bot container     |

Edit `.github/workflows/deploy.yml` if you want different container names.

## Networking

scraper-bot reaches scraper-mcp at `MCP_URL` (read by
`cron/run-digest.js` each run). Under compose it defaults to
`http://host.docker.internal:8080/mcp`; the
`host.docker.internal:host-gateway` host entry (`extra_hosts` in compose,
`--add-host` with `docker run`) exposes the VPS host as a resolvable name
from inside the bot container. On Kubernetes, `k8s/configmap.yaml` sets it
to `http://job-scraper-mcp-service/mcp`.

scraper-mcp listens on the host's port 8080 directly, so anything else
on the VPS (or off it, with firewall rules) can also reach it via that
port.

## ghcr.io image visibility

The first push creates each package as **private**. To let the VPS pull
without authentication:

1. GitHub profile → **Packages** → click each package
2. **Package settings** → **Change visibility** → **Public**

Alternatively, keep them private and run once on the VPS:

```bash
echo $PERSONAL_ACCESS_TOKEN | docker login ghcr.io -u <your-username> --password-stdin
```

with a token that has `read:packages` scope.

## Changing config

Because everything is baked in:

| Want to… | How |
|---|---|
| Change `keyword`, `limit`, `filter` | Edit `config.yaml` → push to `main` |
| Change cron schedule | Edit `bot.schedule` in `config.yaml` → push to `main` (bot Dockerfile reads it via `yq` at build time) |
| Change Discord message format | Edit `prompts/response_template.md` → push to `main`. Read each run, but baked into the bot image, so it changes only with the rebuild/deploy |
| Change requirements bullets | Edit `REQ_MAX_ITEMS` (default 5 bullets per job) / `REQ_MAX_ITEM_CHARS` (default 80 chars per bullet) in `k8s/configmap.yaml` → next run (or `.env`, then recreate the compose bot); no rebuild |
| Change Discord per-message cap | Edit `MAX_CHARS` in `k8s/configmap.yaml` (or `.env`) → affects only the inline fallback; the normal path posts one attachment |
| Change the Discord upload cap | Set `MAX_FILE_BYTES` (default 10 MiB, Discord's non-boosted limit; raise to 50/100 MiB on a boosted guild) |
| Change the MCP endpoint | Edit `MCP_URL` in `k8s/configmap.yaml` (or `.env`; compose defaults it to `http://host.docker.internal:8080/mcp`) → next run |
| Change the scrape timeout | Edit `SCRAPE_TIMEOUT_MS` in `k8s/configmap.yaml` (default 1800000 = 30 min) → next run. It is the only cap on the `scrape_jobs` call |
| Change Discord channel | Update `DISCORD_CHANNEL_ID` GitHub secret → push to main (or manual deploy) |
| Rotate Discord bot token | Update `DISCORD_BOT_TOKEN` secret → push to main |

Note: `update_config` MCP tool writes are still **ephemeral** — useful
for one-shot experiments from an interactive Claude session, but lost on next deploy.
For permanent changes, edit the repo file.

## Manual rollback

To roll back to a previous SHA, trigger the workflow on that older
commit (Actions tab → "Run workflow" → choose ref).

Or directly on the VPS:

```bash
ssh ubuntu@<host>

# MCP rollback
docker pull ghcr.io/orangemangodimz/job-scrapper:mcp-<previous-sha>
docker stop scraper-mcp && docker rm scraper-mcp
docker run -d --name scraper-mcp --restart unless-stopped -p 8080:8080 \
  ghcr.io/orangemangodimz/job-scrapper:mcp-<previous-sha>

# Bot rollback (need to re-supply the bot env)
docker pull ghcr.io/orangemangodimz/job-scrapper:bot-<previous-sha>
docker stop scraper-bot && docker rm scraper-bot
docker run -d --name scraper-bot --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  -e DISCORD_WEBHOOK_URL=... \
  -e MCP_URL=http://host.docker.internal:8080/mcp \
  -e TZ=Asia/Jakarta \
  ghcr.io/orangemangodimz/job-scrapper:bot-<previous-sha>
```

A bot image from before the Node.js pipeline still runs the claude-code CLI
and needs the Claude session mounts it was deployed with.

## Trigger flow

| Action | Result |
|--------|--------|
| Push commit to `main` | All 4 jobs run: build-mcp, build-bot, deploy-mcp, deploy-bot |
| PR merged into `main` | Same |
| Manual run | Actions tab → "Build & Deploy scraper" → Run workflow |
| Push to feature branch / `dev` | No deploy. Use PRs against `dev`, then merge `dev` → `main` for prod |

## Local sanity check

### Quick image build

Build either image locally before pushing to main:

```bash
docker build --target mcp-server -t job-scraper-mcp:local .
docker build --target bot -t job-scraper-bot:local .
```

If both boot, the same Dockerfile targets will build in CI.

The bot's unit tests need only Node 22+:

```bash
cd cron && npm ci && npm test
```

### End-to-end test (skip cron, fire one-shot)

`scripts/test-locally.sh` starts the compose `mcp` profile (mongo +
scraper-mcp) and fires the bot's `run-scraper.sh` once — same code path
supercronic would trigger, but synchronous and immediate.

```bash
export DISCORD_WEBHOOK_URL=<test channel webhook>
./scripts/test-locally.sh
```

It needs `yq` and a `config.dev.patch.yaml`, and loads `.env` if present.
The script:
1. Merges `config.yaml` + `config.dev.patch.yaml` into `/tmp/config.dev.yaml`
2. Builds the `scraper-mcp` and `bot` compose services
3. Starts mongo + scraper-mcp with the dev overlay
4. Waits until `http://localhost:8080/mcp` answers `tools/list`
5. Runs a one-shot bot container executing `run-scraper.sh` (real scrape,
   real Discord post)
6. Stops the MCP stack on exit

If the scrape finds new jobs, the digest lands in the webhook's channel as
one `.md` attachment. `[digest] no new jobs; nothing to post` means nothing
unseen matched.

### Tweaks via env

```bash
REQ_MAX_ITEMS=3 REQ_MAX_ITEM_CHARS=60 ./scripts/test-locally.sh   # tighter requirements bullets
```

Only the variables the compose `bot` service passes through reach the
container (`DISCORD_WEBHOOK_URL`, `MCP_URL`, `SCRAPE_TIMEOUT_MS`, `MAX_CHARS`,
`MAX_FILE_BYTES`, `REQ_MAX_ITEMS`, `REQ_MAX_ITEM_CHARS`, `BOT_VERSION`, `TZ`). Values set in `.env` win over your shell: the
script sources it after.

## Seeding reference data

The `wilayah` collection stores Indonesian administrative area codes
(91 599 rows, Kepmendagri No 300.2.2-2138 Tahun 2025). It is **not**
seeded by the deploy pipeline — run this once on a fresh MongoDB or
after a data refresh.

### Prerequisites

- SSH tunnel to the VPS MongoDB (port 27017) active locally
- Node.js installed locally
- `mongodb` npm package: `npm install -g mongodb` (or local)

### Open tunnel

**DataGrip**: connect the data source — the SSH tunnel stays open while
DataGrip is connected. Note the local port it binds (visible in the
SSH/SSL tab of the data source settings).

**Manual**:
```bash
ssh -L 27017:localhost:27017 ubuntu@43.157.226.237 -N
```

### Run the seeder

```bash
MONGO_URI="mongodb://admin:<MONGO_ROOT_PASSWORD>@127.0.0.1:<LOCAL_PORT>/?authSource=admin" \
NODE_PATH=$(npm root -g) \
node seeds/wilayah.runner.js
```

- `MONGO_ROOT_PASSWORD` — value from your production `.env` / VPS secrets
- `LOCAL_PORT` — `27017` for manual tunnel; check DataGrip SSH/SSL tab if using DataGrip

The script drops the existing `wilayah` collection, inserts all batches,
creates a `nama` index, and verifies the exact row count. It exits
non-zero on mismatch.

## Bot's first run on a new schedule

The bot's crontab default is `0 1 * * *` (daily at 01:00). After the
first deploy, the next scheduled run is whenever cron's clock matches.
To trigger immediately:

```bash
ssh ubuntu@<host>
docker exec scraper-bot /bin/sh /workspace/scraper-bot/cron/run-scraper.sh
```

This runs the same script supercronic would, immediately, in the same
container with the same env.
