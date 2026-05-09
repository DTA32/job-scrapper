#!/bin/sh
LOG=/workspace/scraper-bot/cron/scraper.log
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md

echo "[$(date)] starting multi-site scraper run..." >> "$LOG" 2>&1
cd /workspace/scraper-bot
claude --dangerously-skip-permissions -p "$(cat "$PROMPT")" >> "$LOG" 2>&1
echo "[$(date)] run complete." >> "$LOG" 2>&1
