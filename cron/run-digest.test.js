// node --test run-digest.test.js
//
// The whole run against a real (SDK-built) MCP server and a localhost webhook.

const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { runDigest, wibIsoDate } = require('./run-digest.js');
const { startFakeMcpServer } = require('./test-support/fake-mcp-server.js');
const { startWebhookStub } = require('./test-support/webhook-stub.js');

const NOW = new Date('2026-08-27T04:00:00Z');
const RUN_ID = '66d000000000000000000001';

const scrapeResult = (overrides = {}) => ({
  ok: true,
  keywords: ['backend engineer', 'data analyst'],
  requested_sites: ['glints', 'linkedin'],
  exit_code: 0,
  errors: [],
  results: [
    {
      keyword: 'backend engineer',
      sites: [
        {
          site: 'glints',
          count: 1,
          jobs: [
            {
              site: 'glints',
              title: 'Backend Engineer',
              company: 'ACME',
              location: 'Jakarta',
              url: 'https://glints.com/1',
              posted_date: '2026-08-27',
              requirements: '## About ACME\nWe build logistics software.\n\n## Requirements\n- Go\n- PostgreSQL',
            },
          ],
        },
        {
          site: 'linkedin',
          count: 1,
          jobs: [
            {
              site: 'linkedin',
              title: 'Go Developer',
              company: 'Beta',
              location: null,
              url: 'https://linkedin.com/2',
              posted_date: '2026-08-26T18:30:00Z',
              requirements: 'We are looking for a Go developer to build payment APIs.',
            },
          ],
        },
      ],
    },
    { keyword: 'data analyst', sites: [{ site: 'glints', count: 0, jobs: [] }] },
  ],
  mongo_id: RUN_ID,
  ...overrides,
});

const quietLog = () => {
  const lines = { out: [], err: [] };
  return { lines, log: { log: (m) => lines.out.push(m), error: (m) => lines.err.push(m) } };
};

async function withServices(scrape, fn, { update = async () => ({ ok: true, matched: true }) } = {}) {
  const mcp = await startFakeMcpServer({ scrape_jobs: async () => scrape, update_scrape_run: update });
  const webhook = await startWebhookStub();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'digest-run-'));
  const env = { MCP_URL: mcp.url, DISCORD_WEBHOOK_URL: webhook.url, DIGEST_DIR: dir, BOT_VERSION: 'test' };
  try {
    await fn({ mcp, webhook, dir, env });
  } finally {
    await mcp.close();
    await webhook.close();
  }
}

test('a run scrapes, posts one digest, and records the delivery on the run document', async () => {
  await withServices(scrapeResult(), async ({ mcp, webhook, dir, env }) => {
    const { log } = quietLog();
    const outcome = await runDigest({ env, now: NOW, log });

    assert.equal(outcome.exitCode, 0);
    assert.equal(outcome.status, 'success');
    assert.equal(webhook.requests.length, 1);

    const body = webhook.requests[0].body;
    assert.match(body, /filename="jobs-2026-08-27\.md"/);
    assert.match(body, /Job digest — Thursday, 27 August 2026/);
    assert.match(body, /Scraped 2 jobs across 2 keyword\(s\) and 2 site\(s\) \(bot test\)\. Errors: 0\./);
    assert.match(body, /# backend engineer\n\n## Backend Engineer\nACME \| Jakarta\n/);
    assert.match(body, /\*\*Kualifikasi\*\*\n• Go\n• PostgreSQL/);
    assert.match(body, /## Go Developer\nBeta\n/);
    assert.match(body, /Diposting: Thursday, 27 August 2026\n\n\*\*Ringkasan\*\*\n• We are looking for a Go developer to build payment APIs\./);
    assert.ok(!body.includes('data analyst'), 'a keyword without jobs gets no section');
    assert.ok(fs.existsSync(path.join(dir, 'jobs-2026-08-27.md')));

    assert.deepEqual(mcp.calls, [
      { name: 'scrape_jobs', arguments: {} },
      {
        name: 'update_scrape_run',
        arguments: {
          run_id: RUN_ID,
          patch: {
            discord_sent_status: 'success',
            'run_metadata.bot_post_status': {
              total_posted: 1,
              total_jobs_posted: 2,
              failed: 0,
              delivery_mode: 'attachment',
            },
          },
        },
      },
    ]);
    assert.ok(!JSON.stringify(mcp.calls).includes(env.DISCORD_WEBHOOK_URL), 'webhook URL must never reach Mongo');
  });
});

test('no new jobs: nothing is posted, the run is still recorded as skipped', async () => {
  const empty = scrapeResult({ results: [{ keyword: 'backend engineer', sites: [{ site: 'glints', count: 0, jobs: [] }] }] });
  await withServices(empty, async ({ mcp, webhook, dir, env }) => {
    const outcome = await runDigest({ env, now: NOW, log: quietLog().log });
    assert.equal(outcome.exitCode, 0);
    assert.equal(outcome.status, 'skipped');
    assert.equal(webhook.requests.length, 0);
    assert.deepEqual(fs.readdirSync(dir), []);
    assert.deepEqual(mcp.calls[1].arguments.patch, {
      discord_sent_status: 'skipped',
      'run_metadata.bot_post_status': { total_posted: 0, total_jobs_posted: 0, failed: 0, delivery_mode: 'none' },
    });
  });
});

test('a null mongo_id skips the run-document update', async () => {
  await withServices(scrapeResult({ mongo_id: null }), async ({ mcp, env }) => {
    const { lines, log } = quietLog();
    await runDigest({ env, now: NOW, log });
    assert.deepEqual(mcp.calls.map((c) => c.name), ['scrape_jobs']);
    assert.ok(lines.out.some((l) => /mongo_id is null/.test(l)));
  });
});

test('a failed delivery exits non-zero and is recorded as failed', async () => {
  await withServices(scrapeResult(), async ({ mcp, env }) => {
    const send = async () => ({ mode: 'inline', messages_sent: 2, parts: 1, bytes: 10, failed: 1 });
    const outcome = await runDigest({ env, now: NOW, send, log: quietLog().log });
    assert.equal(outcome.exitCode, 1);
    assert.equal(mcp.calls[1].arguments.patch.discord_sent_status, 'failed');
    assert.deepEqual(mcp.calls[1].arguments.patch['run_metadata.bot_post_status'], {
      total_posted: 2,
      total_jobs_posted: 2,
      failed: 1,
      delivery_mode: 'inline',
    });
  });
});

test('a Mongo update failure is logged but does not fail a delivered run', async () => {
  const update = async () => ({ ok: false, error: 'boom' });
  await withServices(scrapeResult(), async ({ env }) => {
    const { lines, log } = quietLog();
    const outcome = await runDigest({ env, now: NOW, log });
    assert.equal(outcome.exitCode, 0);
    assert.deepEqual(lines.err, ['MongoDB update failed: boom']);
  }, { update });
});

test('a scrape_jobs config error aborts the run before anything is posted', async () => {
  await withServices({ error: 'config file not found: config.yaml' }, async ({ webhook, env }) => {
    await assert.rejects(runDigest({ env, now: NOW, log: quietLog().log }), /scrape_jobs: config file not found/);
    assert.equal(webhook.requests.length, 0);
  });
});

test('a missing webhook URL fails before the scrape starts', async () => {
  await withServices(scrapeResult(), async ({ mcp, env }) => {
    await assert.rejects(runDigest({ env: { ...env, DISCORD_WEBHOOK_URL: '' }, log: quietLog().log }), /DISCORD_WEBHOOK_URL is not set/);
    assert.equal(mcp.calls.length, 0);
  });
});

test('the digest file is named for the WIB date, not the UTC one', () => {
  assert.equal(wibIsoDate(new Date('2026-08-26T17:30:00Z')), '2026-08-27');
});
