#!/usr/bin/env bash
set -euo pipefail

# Build the bot image from Dockerfile.bot and run it once, locally.
#
# With no arguments the container runs its default command, cron/run-scraper.sh:
# a real scrape through the MCP server and a real Discord post. Pass a command to
# run that instead (the manage TUI's Discord test does), e.g.
#   scripts/run_bot_once.sh node /workspace/scraper-bot/cron/run-digest.js
#
# Needs a reachable scraper-mcp, e.g.
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp up --build -d
#
# Env, from .env when present (values there override the shell):
#   DISCORD_WEBHOOK_URL  required
#   MCP_URL              default http://host.docker.internal:8080/mcp
#   TZ                   default Asia/Jakarta
#   SCRAPE_TIMEOUT_MS, MAX_CHARS, MAX_FILE_BYTES, REQ_MAX_ITEMS,
#   REQ_MAX_ITEM_CHARS, BOT_VERSION   passed through when set
#   SKIP_BUILD=1         reuse the existing job-scraper-bot:local image
#
# Usage:
#   ./scripts/run_bot_once.sh [command...]

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="job-scraper-bot:local"
cd "$REPO_ROOT"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
fi

: "${DISCORD_WEBHOOK_URL:?set DISCORD_WEBHOOK_URL (in .env or the environment)}"
export DISCORD_WEBHOOK_URL
export MCP_URL="${MCP_URL:-http://host.docker.internal:8080/mcp}"
export TZ="${TZ:-Asia/Jakarta}"

if [ "${SKIP_BUILD:-}" != "1" ]; then
  echo "==> Building ${IMAGE} from Dockerfile.bot..."
  docker build -f Dockerfile.bot -t "$IMAGE" .
fi

# `-e NAME` with no value copies NAME from this shell, so secrets never appear on the
# command line. Optional knobs are only passed when set, keeping the image defaults.
env_args=(-e DISCORD_WEBHOOK_URL -e MCP_URL -e TZ)
for name in SCRAPE_TIMEOUT_MS MAX_CHARS MAX_FILE_BYTES REQ_MAX_ITEMS REQ_MAX_ITEM_CHARS BOT_VERSION; do
  if [ -n "${!name:-}" ]; then
    export "${name?}"
    env_args+=(-e "$name")
  fi
done

echo "==> Running ${IMAGE} once (MCP_URL=${MCP_URL})..."
# host-gateway makes host.docker.internal resolve on Linux too; Docker Desktop has it built in.
exec docker run --rm --add-host=host.docker.internal:host-gateway "${env_args[@]}" "$IMAGE" "$@"
