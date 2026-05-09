#!/bin/sh
set -e

SUPERCRONIC="/workspace/scraper-bot/cron/supercronic"
SUPERCRONIC_URL="https://github.com/aptible/supercronic/releases/latest/download/supercronic-linux-amd64"

if [ ! -f "$SUPERCRONIC" ]; then
  echo "Downloading supercronic..."
  if command -v curl > /dev/null 2>&1; then
    curl -fsSL "$SUPERCRONIC_URL" -o "$SUPERCRONIC"
  elif command -v wget > /dev/null 2>&1; then
    wget -O "$SUPERCRONIC" "$SUPERCRONIC_URL"
  else
    echo "ERROR: neither curl nor wget found" >&2
    exit 1
  fi
  chmod +x "$SUPERCRONIC"
fi

exec "$SUPERCRONIC" /workspace/scraper-bot/cron/scraper-crontab
