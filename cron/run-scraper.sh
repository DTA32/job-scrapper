#!/bin/sh
# Cron entrypoint: runs claude-code with a markdown prompt, logs all output
LOG=/workspace/scraper-bot/cron/scraper.log
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md

echo "[$(date)] starting multi-site scraper run..." | tee -a "$LOG"
cd /workspace/scraper-bot
# --dangerously-skip-permissions: needed for unattended cron — no TTY to approve prompts
claude --dangerously-skip-permissions -p "$(cat "$PROMPT")" 2>&1 | tee -a "$LOG"
EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "[$(date)] ERROR: claude exited with code $EXIT_CODE" | tee -a "$LOG" >&2
fi

echo "[$(date)] run complete." | tee -a "$LOG"
