# Kubernetes deployment (homeserver)

Runbook for deploying the job scraper to a single-node homeserver Kubernetes
cluster. This replaces the docker-compose + supercronic setup.

## What gets deployed

| Manifest | Resource | Purpose |
|----------|----------|---------|
| `deployment.yaml` | Deployment `job-scraper-mcp` | Long-running MCP HTTP server (port 8080) |
| `service.yaml` | Service `job-scraper-mcp-service` | ClusterIP so the bot reaches the MCP in-cluster |
| `cronjob.yaml` | CronJob `job-scraper-bot` | Daily digest: `cron/run-digest.js` scrapes via the MCP service, posts to Discord, records the run |
| `configmap.yaml` | ConfigMap `job-scraper-config` | Non-secret env (MCP_URL, SCRAPE_TIMEOUT_MS, DB name, TZ, MAX_CHARS, REQ_MAX_ITEMS, REQ_MAX_ITEM_CHARS) |
| `secret.example.yaml` | Secret `job-scraper-secret` | Template for `MONGO_URI` (Atlas) + `DISCORD_WEBHOOK_URL`; copy to `secret.yaml` (gitignored) |

MongoDB is **MongoDB Atlas (cloud)** — there is no Mongo manifest. The MCP server
reaches job sites and Atlas directly from the homeserver's residential IP; no
SSH tunnel / SOCKS proxy is used.

## Images

Two images are built from this repo (a shared Python base plus the two runtime
images). Manifests use the placeholder `image: replacedbycicd`; the deploy step
below rewrites it. `deployment.yaml` gets the **mcp** image, `cronjob.yaml` gets
the **bot** image.

```sh
TAG=$(git rev-parse --short HEAD)

# 1. shared Python base (built first; the mcp/cli images start FROM it)
docker build -f Dockerfile.base        -t job-scraper-base .

# 2. runtime images
docker build -f Dockerfile.mcp         -t dta32/job-scraper-mcp:$TAG .
docker build --target bot              -t dta32/job-scraper-bot:$TAG .   # root Dockerfile, node-only bot stage
# optional local-testing CLI image:
# docker build -f Dockerfile.scraper-cli -t dta32/job-scraper-cli:$TAG .

docker push dta32/job-scraper-mcp:$TAG
docker push dta32/job-scraper-bot:$TAG
```

## One-time host / cluster setup

1. **Secret.** Copy the template, fill in real values, then apply it:
   ```sh
   cp secret.example.yaml secret.yaml
   # edit secret.yaml: MONGO_URI, DISCORD_WEBHOOK_URL
   ```
   `secret.yaml` is gitignored, so real credentials cannot be committed; only
   `secret.example.yaml` (placeholders) is tracked.

2. **Seed the `wilayah` collection into Atlas** (optional; improves the location
   filter — the scraper degrades to substring matching without it):
   ```sh
   MONGO_URI="mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority" \
     ./seed.sh
   ```

## Deploy

```sh
TAG=$(git rev-parse --short HEAD)
sed -i.bak "s#replacedbycicd#dta32/job-scraper-mcp:$TAG#" deployment.yaml
sed -i.bak "s#replacedbycicd#dta32/job-scraper-bot:$TAG#" cronjob.yaml

kubectl apply -f secret.yaml \
              -f configmap.yaml \
              -f deployment.yaml \
              -f service.yaml \
              -f cronjob.yaml

# restore the placeholders (don't commit the rewritten tags)
mv deployment.yaml.bak deployment.yaml
mv cronjob.yaml.bak cronjob.yaml
```

Validate manifests without a cluster: `kubectl apply --dry-run=client -f .`

## Trigger & observe

```sh
# run the daily job on demand
kubectl create job --from=cronjob/job-scraper-bot manual-run
kubectl logs -f job/manual-run                     # scrape -> format -> webhook posts

# MCP server health (from your workstation)
kubectl port-forward svc/job-scraper-mcp-service 8080:80
curl -s localhost:8080/health
```

## Notes

- **CI later.** `.github/workflows/deploy.yml` (the old VPS/compose pipeline) is
  intentionally left untouched. When wiring up a new CI, have it perform the same
  three steps as *Deploy* above: build+push both images, `sed` the tag into each
  manifest, `kubectl apply`.
- **Schedule.** `cronjob.yaml` (`schedule: "0 11 * * *"`, `timeZone:
  "Asia/Jakarta"`) is the source of truth. `config.yaml`'s `bot.schedule` is now
  informational only.
- **Upgrading from the claude-code bot.** The bot no longer mounts a Claude session.
  Once a run on the new image has posted, remove what the old one needed:
  `kubectl delete pvc job-scraper-claude-pvc && kubectl delete pv job-scraper-claude-pv`,
  then wipe `/mnt/data/job-scraper-claude` on the node, which holds a logged-in session.
- **Dedup.** Cross-run deduplication is handled server-side by the MCP
  `scrape_jobs` tool (Mongo `seen_jobs` collection); the bot just posts what it
  is given. Tune `max_pages` / `page_delay_sec` in `config.yaml`.
