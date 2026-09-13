#!/usr/bin/env node
// One scheduled digest run, end to end, with no model in the loop:
//
//   1. call scrape_jobs on the job-scraper MCP server
//   2. render every job through prompts/response_template.md (lib/format.js),
//      with the requirements bullets picked by lib/requirements.js
//   3. write jobs-<WIB date>.md and post it to Discord (send-digest.js)
//   4. record the delivery outcome on the run's Mongo document (update_scrape_run)
//
// Env:
//   DISCORD_WEBHOOK_URL   required
//   MCP_URL               job-scraper MCP endpoint (default http://job-scraper-mcp-service/mcp)
//   SCRAPE_TIMEOUT_MS     cap on the scrape_jobs call (default 30 minutes)
//   TEMPLATE_PATH         per-job template (default ../prompts/response_template.md)
//   DIGEST_DIR            where the digest file is written (default the OS temp dir)
//   BOT_VERSION           optional, shown in the summary line
//   REQ_MAX_ITEMS, REQ_MAX_ITEM_CHARS   requirements bullet caps (default 5, 80)
//   MAX_FILE_BYTES, MAX_CHARS           upload split + inline fallback caps
//
// Exits non-zero when the scrape could not run or a Discord message failed.

const fs = require('fs');
const os = require('os');
const path = require('path');

const mcp = require('./lib/mcp.js');
const { buildDigest, buildSummary, countJobs } = require('./lib/format.js');
const requirements = require('./lib/requirements.js');
const { sendDigest } = require('./send-digest.js');

const DEFAULT_MCP_URL = 'http://job-scraper-mcp-service/mcp';
const DEFAULT_TEMPLATE_PATH = path.join(__dirname, '..', 'prompts', 'response_template.md');
const UPDATE_TIMEOUT_MS = 30 * 1000;
const NOTHING_SENT = { mode: 'none', messages_sent: 0, parts: 0, bytes: 0, failed: 0 };

function positiveInt(raw) {
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

/** YYYY-MM-DD of `now` in WIB, for the digest file name. */
function wibIsoDate(now) {
  const parts = {};
  const format = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Jakarta',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  for (const { type, value } of format.formatToParts(now)) parts[type] = value;
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/**
 * Run one digest. Resolves {exitCode, status, jobs, delivery}; rejects only when
 * the run cannot start (no webhook, MCP unreachable, scrape_jobs failing outright).
 */
async function runDigest({ env = process.env, now = new Date(), send = sendDigest, log = console } = {}) {
  const webhookUrl = env.DISCORD_WEBHOOK_URL;
  if (!webhookUrl) throw new Error('DISCORD_WEBHOOK_URL is not set');
  const mcpUrl = env.MCP_URL || DEFAULT_MCP_URL;
  const timeoutMs = positiveInt(env.SCRAPE_TIMEOUT_MS) || mcp.DEFAULT_TIMEOUT_MS;
  const template = fs.readFileSync(env.TEMPLATE_PATH || DEFAULT_TEMPLATE_PATH, 'utf8');
  const requirementOptions = requirements.optionsFromEnv(env);

  const client = await mcp.connect(mcpUrl, { timeoutMs });
  try {
    log.log(`[digest] calling scrape_jobs on ${mcpUrl} (timeout ${Math.round(timeoutMs / 1000)}s)`);
    const result = await client.callTool('scrape_jobs', {});
    // scrape_jobs answers a config problem with {error} instead of a run.
    if (typeof result.error === 'string') throw new Error(`scrape_jobs: ${result.error}`);

    const jobs = countJobs(result);
    const errors = Array.isArray(result.errors) ? result.errors.length : 0;
    log.log(`[digest] scraped ${jobs} job(s), ${errors} error(s), mongo_id=${result.mongo_id ?? 'null'}`);

    let delivery = NOTHING_SENT;
    let jobsPosted = 0;
    let status = 'skipped';
    if (jobs === 0) {
      // Nothing new since the last run: no file and no post, which beats a noisy "0 jobs".
      log.log('[digest] no new jobs; nothing to post');
    } else {
      const { markdown, jobCount } = buildDigest(result, template, {
        renderRequirements: (outline) => requirements.renderRequirements(outline, requirementOptions),
      });
      const digestPath = path.join(env.DIGEST_DIR || os.tmpdir(), `jobs-${wibIsoDate(now)}.md`);
      fs.writeFileSync(digestPath, markdown);
      jobsPosted = jobCount;
      try {
        delivery = await send({
          webhookUrl,
          digestPath,
          summary: buildSummary(result, { now, botVersion: env.BOT_VERSION }),
          maxFileBytes: positiveInt(env.MAX_FILE_BYTES),
          maxChars: positiveInt(env.MAX_CHARS),
        });
      } catch (err) {
        log.error(`[digest] send failed: ${err.message}`);
        delivery = { ...NOTHING_SENT, failed: 1 };
      }
      status = delivery.failed > 0 ? 'failed' : 'success';
      log.log(`RESULT ${JSON.stringify(delivery)}`);
    }

    await recordDelivery(client, result.mongo_id, {
      discord_sent_status: status,
      'run_metadata.bot_post_status': {
        total_posted: delivery.messages_sent,
        total_jobs_posted: jobsPosted,
        failed: delivery.failed,
        delivery_mode: delivery.mode,
      },
    }, log);

    return { exitCode: delivery.failed > 0 ? 1 : 0, status, jobs, delivery };
  } finally {
    await client.close();
  }
}

/**
 * Add the Discord columns to the run document scrape_jobs inserted. Posting has
 * already happened and takes priority, so a failure here is logged, never thrown.
 * The patch never carries the webhook URL: it embeds a secret token.
 */
async function recordDelivery(client, mongoId, patch, log) {
  if (!mongoId) {
    log.log('[digest] mongo_id is null (Mongo was unreachable during the scrape); run not recorded');
    return;
  }
  try {
    const outcome = await client.callTool('update_scrape_run', { run_id: mongoId, patch }, { timeout: UPDATE_TIMEOUT_MS });
    if (!outcome.ok) log.error(`MongoDB update failed: ${outcome.error}`);
    else if (!outcome.matched) log.error(`MongoDB update failed: no run document ${mongoId}`);
  } catch (err) {
    log.error(`MongoDB update failed: ${err.message}`);
  }
}

if (require.main === module) {
  runDigest()
    .then(({ exitCode }) => {
      process.exitCode = exitCode;
    })
    .catch((err) => {
      console.error(`[digest] run failed: ${err.message}`);
      process.exitCode = 1;
    });
}

module.exports = { runDigest, wibIsoDate, DEFAULT_MCP_URL };
