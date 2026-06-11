#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

_env() { grep -E "^${1}=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-; }

MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_USER="${MONGO_ROOT_USER:-$(_env MONGO_ROOT_USER)}"
MONGO_USER="${MONGO_USER:-admin}"
MONGO_PASS="${MONGO_ROOT_PASSWORD:-$(_env MONGO_ROOT_PASSWORD)}"

if [[ -z "${MONGO_PASS}" ]]; then
  echo "ERROR: MONGO_ROOT_PASSWORD not set and not found in .env" >&2
  exit 1
fi

export MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASS}@${MONGO_HOST}:${MONGO_PORT}/?authSource=admin"

echo "[seed] target: ${MONGO_HOST}:${MONGO_PORT} (user=${MONGO_USER})"

NODE_PATH="$(npm root -g 2>/dev/null || true)" node "${SCRIPT_DIR}/seeds/wilayah.runner.js"

echo "[seed] all done"
