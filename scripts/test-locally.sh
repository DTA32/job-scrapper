#!/usr/bin/env bash
set -euo pipefail

# One-shot local test of the scrape → Discord post flow.
# Skips supercronic and fires `cron/run-scraper.sh` directly inside a
# fresh bot container. Requires:
#
#   DISCORD_BOT_TOKEN   - bot token with Send Messages perm in target channel
#   DISCORD_CHANNEL_ID  - channel ID to post into
#   ~/.claude           - your local Claude Code session config dir
#   ~/.claude.json      - your local Claude Code config file
#
# Usage:
#   export DISCORD_BOT_TOKEN=...
#   export DISCORD_CHANNEL_ID=...
#   ./scripts/test-locally.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CLAUDE_CONFIG_FILE="${CLAUDE_CONFIG_FILE:-$HOME/.claude.json}"

: "${DISCORD_BOT_TOKEN:?set DISCORD_BOT_TOKEN before running}"
: "${DISCORD_CHANNEL_ID:?set DISCORD_CHANNEL_ID before running}"

if [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
  echo "Claude config dir not found at $CLAUDE_CONFIG_DIR" >&2
  echo "Run 'claude login' first, or set CLAUDE_CONFIG_DIR to your config path" >&2
  exit 1
fi
if [ ! -f "$CLAUDE_CONFIG_FILE" ]; then
  echo "Claude config file not found at $CLAUDE_CONFIG_FILE" >&2
  exit 1
fi

MCP_NAME="${MCP_NAME:-scraper-mcp-test}"
BOT_TAG="${BOT_TAG:-job-scraper-bot:local}"
MCP_TAG="${MCP_TAG:-job-scraper-mcp:local}"

echo "==> Building MCP image..."
docker build --target mcp-server -t "$MCP_TAG" .

echo "==> Building bot image..."
docker build --target bot -t "$BOT_TAG" .

echo "==> Cleaning up any prior MCP test container..."
docker rm -f "$MCP_NAME" 2>/dev/null || true

echo "==> Starting MCP server on host port 8080..."
docker run -d \
  --name "$MCP_NAME" \
  -p 8080:8080 \
  "$MCP_TAG"

cleanup() {
  echo "==> Stopping MCP test container..."
  docker rm -f "$MCP_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Waiting for MCP to be ready..."
for i in $(seq 1 20); do
  if curl -sf -o /dev/null -X POST -H 'Accept: application/json, text/event-stream' \
      -H 'Content-Type: application/json' \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
      http://localhost:8080/mcp; then
    break
  fi
  if ! docker ps --filter "name=$MCP_NAME" --filter "status=running" -q | grep -q .; then
    echo "MCP container died. Logs:" >&2
    docker logs "$MCP_NAME" >&2
    exit 1
  fi
  sleep 1
done
echo "==> MCP is up."

echo "==> Firing bot one-shot (skipping supercronic, running run-scraper.sh directly)..."
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -v "$CLAUDE_CONFIG_DIR:/home/node/.claude" \
  -v "$CLAUDE_CONFIG_FILE:/home/node/.claude.json" \
  -e DISCORD_BOT_TOKEN="$DISCORD_BOT_TOKEN" \
  -e DISCORD_CHANNEL_ID="$DISCORD_CHANNEL_ID" \
  --entrypoint /bin/sh \
  "$BOT_TAG" \
  /workspace/scraper-bot/cron/run-scraper.sh

echo "==> Done. MCP container will now be removed by trap."
