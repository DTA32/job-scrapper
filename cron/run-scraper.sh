#!/bin/sh
# Cron entrypoint: runs one digest (scrape via MCP -> Discord -> Mongo) and logs all output.
# POSIX sh (not bash): the k8s CronJob and scripts/run_bot_once.sh run this as
# `/bin/sh run-scraper.sh`, and the bot image's /bin/sh is dash — so no bashisms
# (e.g. ${PIPESTATUS}).
#
# All configuration is environment (MCP_URL, DISCORD_WEBHOOK_URL, SCRAPE_TIMEOUT_MS,
# REQ_MAX_ITEMS, ...), injected by the k8s ConfigMap/Secret or scripts/run_bot_once.sh. The
# header of cron/run-digest.js lists every variable.
LOG=/workspace/scraper-bot/cron/scraper.log
DIGEST=/workspace/scraper-bot/cron/run-digest.js

echo "[$(date)] starting multi-site scraper run..." | tee -a "$LOG"
cd /workspace/scraper-bot
# Stream the run's output to console + log, but capture *node's* exit (not tee's).
# POSIX sh has no ${PIPESTATUS}, so route the real rc through a file.
{
  node "$DIGEST" 2>&1
  echo "$?" >"$LOG.rc"
} | tee -a "$LOG"
EXIT_CODE="$(cat "$LOG.rc")"; rm -f "$LOG.rc"

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "[$(date)] ERROR: digest run exited with code $EXIT_CODE" | tee -a "$LOG" >&2
fi

echo "[$(date)] run complete." | tee -a "$LOG"
# Exit 0 even when the run failed, as the claude-based entrypoint did: the CronJob
# restarts on failure, and a retry would scrape again after this run's jobs were
# already marked seen (and possibly posted). The ERROR line above is the signal.
exit 0
