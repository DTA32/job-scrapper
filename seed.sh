#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
SEEDS_DIR="${SCRIPT_DIR}/seeds"

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

URI="mongodb://${MONGO_USER}:${MONGO_PASS}@${MONGO_HOST}:${MONGO_PORT}/?authSource=admin"

echo "[seed] target: ${MONGO_HOST}:${MONGO_PORT} (user=${MONGO_USER})"

shopt -s nullglob
seeds=("${SEEDS_DIR}"/*.mongosh.js)
shopt -u nullglob

if [[ ${#seeds[@]} -eq 0 ]]; then
  echo "ERROR: no *.mongosh.js files found in seeds/" >&2
  exit 1
fi

for f in "${seeds[@]}"; do
  echo "[seed] >>> $(basename "${f}")"
  mongosh "${URI}" "${f}"
done

echo "[seed] all done"
