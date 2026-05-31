#!/bin/sh
# Cron entrypoint: runs claude-code with a markdown prompt, logs all output.
# POSIX sh (not bash): supercronic/docker invoke this as `/bin/sh run-scraper.sh`,
# and the bot image's /bin/sh is dash — so no bashisms (e.g. ${PIPESTATUS}).
LOG=/workspace/scraper-bot/cron/scraper.log
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md

echo "[$(date)] starting multi-site scraper run..." | tee -a "$LOG"
cd /workspace/scraper-bot
# --dangerously-skip-permissions: needed for unattended cron — no TTY to approve prompts
# Stream claude output to console + log, but capture *claude's* exit (not tee's).
# POSIX sh has no ${PIPESTATUS}, so route the real rc through a file.
{ claude --dangerously-skip-permissions -p "$(cat "$PROMPT")" 2>&1; echo "$?" >"$LOG.rc"; } | tee -a "$LOG"
EXIT_CODE="$(cat "$LOG.rc")"; rm -f "$LOG.rc"

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "[$(date)] ERROR: claude exited with code $EXIT_CODE" | tee -a "$LOG" >&2
fi

echo "[$(date)] run complete." | tee -a "$LOG"
