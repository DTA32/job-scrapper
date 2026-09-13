# Deploy pipeline

GitHub Actions builds the **scraper-mcp** Docker image, pushes it to
GitHub Container Registry, and SSHs into the VPS to (re)create the
`scraper-mcp` container. It also runs the bot's unit tests; it neither
builds nor deploys the bot.

Trigger: push to `main` (or manual via "Run workflow" in the Actions tab).

**Fully isolated**: nothing on the VPS host beyond docker itself. No
mounted files, no state directories, no manual config. Each deploy
starts the container fresh from the new image. Configuration baked into
the image at build time; secrets injected as env vars by the deploy job.

**The bot is not deployed here.** It is built from `Dockerfile.bot` and runs
as the Kubernetes CronJob `job-scraper-bot`; see `k8s/README.md` and
[`orchestration.md`](orchestration.md). To fire a run now:
`kubectl create job --from=cronjob/job-scraper-bot manual-run`.

## What ships

| Image | Container | Role |
|---|---|---|
| `ghcr.io/<owner>/<repo>:mcp-<sha>` | `scraper-mcp` | FastMCP HTTP server on port 8080 |

Also tagged as `:mcp-latest`.

## What the pipeline does

1. **build-mcp** — build `mcp-server` Dockerfile target → push
2. **deploy-mcp** — SSH, `docker pull` + replace `scraper-mcp` container (after build-mcp)
3. **test-bot** — `npm ci && npm test` in `cron/` on Node 22; standalone, gates nothing

## Required GitHub secrets

Repo → Settings → Secrets and variables → Actions → **Secrets** tab.

| Secret | Used by | Value |
|---|---|---|
| `SSH_HOST` | deploy-mcp | `43.157.226.237` |
| `SSH_USER` | deploy-mcp | `ubuntu` |
| `SSH_PRIVATE_KEY` | deploy-mcp | private key for VPS SSH |
| `MONGO_ROOT_PASSWORD` | deploy-mcp | MongoDB root password |

`GITHUB_TOKEN` is auto-provided — used to push to ghcr.io.

## GitHub variables

None are required. Same UI, **Variables** tab (plain text, visible in
logs): the workflow reads `MONGO_ROOT_USER`, `MONGO_DB_NAME` and
`MONGO_COLLECTION_NAME` in deploy-mcp, each with a default.

## Hardcoded values (workflow env block)

| Var               | Default       | Purpose                          |
|-------------------|---------------|----------------------------------|
| MCP `CONTAINER_NAME` | `scraper-mcp` | Name of the MCP container     |

Edit `.github/workflows/deploy.yml` if you want different container names.

## Networking

scraper-mcp listens on the host's port 8080 directly, so anything else
on the VPS (or off it, with firewall rules) can also reach it via that
port.

The bot does not run on the VPS. It reads its endpoint from `MCP_URL`
(`cron/run-digest.js`, each run). On Kubernetes, `k8s/configmap.yaml` sets
it to `http://job-scraper-mcp-service/mcp`. A local
`scripts/run_bot_once.sh` run defaults it to
`http://host.docker.internal:8080/mcp` and passes
`--add-host=host.docker.internal:host-gateway`, which makes that name
resolve to the host on Linux. See
[`orchestration.md`](orchestration.md#how-scraper-mcp-is-reached).

## ghcr.io image visibility

The first push creates the package as **private**. To let the VPS pull
without authentication:

1. GitHub profile → **Packages** → click the package
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
| Change cron schedule | Edit `schedule` in `k8s/cronjob.yaml` → re-apply the manifest (see `k8s/README.md`). `bot.schedule` in `config.yaml` is informational only |
| Change Discord message format | Edit `prompts/response_template.md` → rebuild the bot image from `Dockerfile.bot` and bump the CronJob's `image` (see `k8s/README.md`). Read each run, but baked into the bot image, so it changes only with the rebuild |
| Change requirements bullets | Edit `REQ_MAX_ITEMS` (default 5 bullets per job) / `REQ_MAX_ITEM_CHARS` (default 80 chars per bullet) in `k8s/configmap.yaml` → next run (locally: `.env`, next `scripts/run_bot_once.sh`); no rebuild |
| Change Discord per-message cap | Edit `MAX_CHARS` in `k8s/configmap.yaml` (or `.env`) → affects only the inline fallback; the normal path posts one attachment |
| Change the Discord upload cap | Set `MAX_FILE_BYTES` (default 10 MiB, Discord's non-boosted limit; raise to 50/100 MiB on a boosted guild) |
| Change the MCP endpoint | Edit `MCP_URL` in `k8s/configmap.yaml` (or `.env`; `scripts/run_bot_once.sh` defaults it to `http://host.docker.internal:8080/mcp`) → next run |
| Change the scrape timeout | Edit `SCRAPE_TIMEOUT_MS` in `k8s/configmap.yaml` (default 1800000 = 30 min) → next run. It is the only cap on the `scrape_jobs` call |
| Change Discord channel | Point `DISCORD_WEBHOOK_URL` at a webhook in that channel: the `job-scraper-secret` Secret (`k8s/secret.yaml`, re-applied) → next run; locally, `.env` |

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
```

The bot rolls back on Kubernetes instead: point the CronJob's `image` at the
previous tag and re-apply the manifest (see `k8s/README.md`).

## Trigger flow

| Action | Result |
|--------|--------|
| Push commit to `main` | All 3 jobs run: build-mcp, deploy-mcp, test-bot |
| PR merged into `main` | Same |
| Manual run | Actions tab → "Build & Deploy scraper" → Run workflow |
| Push to feature branch / `dev` | No deploy. Use PRs against `dev`, then merge `dev` → `main` for prod |

## Local sanity check

### Quick image build

Build either image locally before pushing to main:

```bash
docker build --target mcp-server -t job-scraper-mcp:local .
docker build -f Dockerfile.bot -t job-scraper-bot:local .
```

If the first builds, `build-mcp` will build the same root Dockerfile target
in CI. The bot image is built from `Dockerfile.bot` for the CronJob
(`k8s/README.md`).

The bot's unit tests need only Node 22+ (CI's `test-bot` job runs the same):

```bash
cd cron && npm ci && npm test
```

### End-to-end test (skip cron, fire one-shot)

`scripts/test-locally.sh` starts the compose `mcp` profile (mongo +
scraper-mcp) and runs `scripts/run_bot_once.sh` — the bot image's default
command, the same `run-scraper.sh` the CronJob runs, but synchronous and
immediate.

```bash
export DISCORD_WEBHOOK_URL=<test channel webhook>   # or set it in .env
./scripts/test-locally.sh
```

It needs `yq` and a `config.dev.patch.yaml`. The script:
1. Merges `config.yaml` + `config.dev.patch.yaml` into `/tmp/config.dev.yaml`
2. Builds and starts mongo + scraper-mcp (compose `mcp` profile, dev
   overlay), which publishes `:8080`
3. Waits for the MCP endpoint at `http://localhost:8080/mcp`
4. Runs `scripts/run_bot_once.sh`: builds `job-scraper-bot:local` from
   `Dockerfile.bot`, then runs it once with `docker run --rm
   --add-host=host.docker.internal:host-gateway` (real scrape, real
   Discord post)
5. Stops the MCP stack on exit

`scripts/test_cron_dev.sh` does the same against the dev stack: it requires
`.env`, reuses an already-running dev stack or starts one, runs
`scripts/run_bot_once.sh`, and tears the stack down only if it started it.

If the scrape finds new jobs, the digest lands in the webhook's channel as
one `.md` attachment. `[digest] no new jobs; nothing to post` means nothing
unseen matched.

### Tweaks via env

```bash
REQ_MAX_ITEMS=3 REQ_MAX_ITEM_CHARS=60 ./scripts/test-locally.sh   # tighter requirements bullets
SKIP_BUILD=1 ./scripts/run_bot_once.sh                             # rerun the bot without rebuilding its image
```

Only the variables `scripts/run_bot_once.sh` passes reach the container:
`DISCORD_WEBHOOK_URL` (required), `MCP_URL` (default
`http://host.docker.internal:8080/mcp`), `TZ` (default `Asia/Jakarta`), and
`SCRAPE_TIMEOUT_MS`, `MAX_CHARS`, `MAX_FILE_BYTES`, `REQ_MAX_ITEMS`,
`REQ_MAX_ITEM_CHARS`, `BOT_VERSION` when set. Values set in `.env` win over
your shell: the script sources it from the repo root if present.

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
