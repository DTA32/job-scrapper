#!/usr/bin/env bash
set -euo pipefail

# Start the dev environment (no proxy, config merged from config.yaml + config.dev.patch.yaml).
#
# Usage:
#   ./scripts/run_dev.sh           # both mcp + bot
#   ./scripts/run_dev.sh mcp       # MCP server only
#   ./scripts/run_dev.sh bot       # bot only

# --- config ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.dev.yml"
MERGED_CONFIG="/tmp/config.dev.yaml"
ARG="${1:-all}"

# --- guards ---
if ! command -v yq &>/dev/null; then
  echo "ERROR: yq not found — install it first: https://github.com/mikefarah/yq" >&2
  exit 1
fi

# --- merge config ---
echo "==> Merging config.yaml + config.dev.patch.yaml -> ${MERGED_CONFIG}..."
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  "$REPO_ROOT/config.yaml" \
  "$REPO_ROOT/config.dev.patch.yaml" \
  > "$MERGED_CONFIG"

# --- resolve profiles ---
case "$ARG" in
  mcp)  PROFILES="--profile mcp" ;;
  bot)  PROFILES="--profile bot" ;;
  all)  PROFILES="--profile mcp --profile bot" ;;
  *)
    echo "Usage: $0 [mcp|bot]" >&2
    exit 1
    ;;
esac

# --- run ---
cd "$REPO_ROOT"

echo "==> Starting dev environment (no proxy, services: ${ARG})..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" $PROFILES up --build -d
