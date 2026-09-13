// node --test lib/format.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const {
  buildDigest,
  buildSummary,
  formatPostedDate,
  formatWibDate,
  renderJob,
} = require('./format.js');
const { JOB_SEPARATOR } = require('../send-digest.js');

const TEMPLATE = fs.readFileSync(path.join(__dirname, '..', '..', 'prompts', 'response_template.md'), 'utf8');
const bullets = (outline) => (outline ? '**Kualifikasi**\n• Go' : null);

const fullJob = {
  site: 'glints',
  title: 'Backend Engineer',
  company: 'ACME',
  location: 'Jakarta',
  url: 'https://example.com/1',
  posted_date: '2026-08-27',
  salary: 'IDR 10-15jt',
  employment_type: 'full-time',
  work_type: 'hybrid',
  experience_level: '1-3 years',
  requirements: '## Requirements\n- Go',
};

test('posted_date: bare dates are WIB already and are not shifted', () => {
  // 27 August 2026 is a Thursday (matches the last model-made digest title).
  assert.equal(formatPostedDate('2026-08-27'), 'Thursday, 27 August 2026');
  assert.equal(formatPostedDate('2026-09-03'), 'Thursday, 03 September 2026');
});

test('posted_date: zoned timestamps convert to the WIB day', () => {
  assert.equal(formatPostedDate('2026-08-26T18:30:00Z'), 'Thursday, 27 August 2026');
  assert.equal(formatPostedDate('2026-08-26T16:59:59.929Z'), 'Wednesday, 26 August 2026');
  assert.equal(formatPostedDate('2026-08-27T05:00:00+00:00'), 'Thursday, 27 August 2026');
  assert.equal(formatPostedDate('2026-08-27T23:30:00+0700'), 'Thursday, 27 August 2026');
});

test('posted_date: zone-less timestamps keep their calendar day', () => {
  assert.equal(formatPostedDate('2026-08-27T23:30:00'), 'Thursday, 27 August 2026');
});

test('posted_date: anything unparseable passes through unchanged', () => {
  assert.equal(formatPostedDate('kemarin'), 'kemarin');
  assert.equal(formatPostedDate('2026-02-30'), '2026-02-30');
  assert.equal(formatPostedDate(null), null);
});

test('formatWibDate uses the WIB day for the title', () => {
  assert.equal(formatWibDate(new Date('2026-08-26T17:00:00Z')), 'Thursday, 27 August 2026');
});

test('a fully populated job renders every template line', () => {
  assert.equal(
    renderJob(TEMPLATE, fullJob, { renderRequirements: bullets }),
    [
      '## Backend Engineer',
      'ACME | Jakarta',
      '',
      '**Details**',
      'Link: [link](https://example.com/1)',
      'Source: glints',
      'Diposting: Thursday, 27 August 2026',
      'Gaji: IDR 10-15jt',
      'Tipe: full-time | hybrid',
      'Pengalaman: 1-3 years',
      '',
      '**Kualifikasi**',
      '• Go',
    ].join('\n'),
  );
});

test('null fields drop the placeholder, its separator, and label-only lines', () => {
  const job = {
    ...fullJob,
    location: null,
    posted_date: null,
    salary: '  ',
    employment_type: null,
    experience_level: undefined,
    requirements: null,
  };
  assert.equal(
    renderJob(TEMPLATE, job, { renderRequirements: bullets }),
    [
      '## Backend Engineer',
      'ACME',
      '',
      '**Details**',
      'Link: [link](https://example.com/1)',
      'Source: glints',
      'Tipe: hybrid',
    ].join('\n'),
  );
});

test('the right-hand field of a pair can be the missing one', () => {
  const out = renderJob(TEMPLATE, { ...fullJob, work_type: null }, { renderRequirements: bullets });
  assert.match(out, /^Tipe: full-time$/m);
});

test('a section header whose whole body dropped is removed with it', () => {
  const template = '## {title}\n\n**Contact**\nEmail: {email}\nPhone: {phone}\n\n**Details**\nSource: {site}';
  assert.equal(
    renderJob(template, { title: 'Dev', site: 'indeed' }),
    '## Dev\n\n**Details**\nSource: indeed',
  );
});

test('values containing braces are not re-expanded', () => {
  const out = renderJob('## {title}\nSource: {site}', { title: 'Use {site} wisely', site: 'glints' });
  assert.equal(out, '## Use {site} wisely\nSource: glints');
});

test('digest has one section per keyword with jobs, separated by the job separator', () => {
  const result = {
    results: [
      {
        keyword: 'backend engineer',
        sites: [
          { site: 'glints', count: 1, jobs: [{ title: 'A', company: 'X', url: 'u1', site: 'glints' }] },
          { site: 'indeed', count: 0, jobs: [] },
          { site: 'linkedin', count: 1, jobs: [{ title: 'B', company: 'Y', url: 'u2', site: 'linkedin' }] },
        ],
      },
      { keyword: 'data analyst', sites: [{ site: 'glints', count: 0, jobs: [] }] },
      {
        keyword: 'ai engineer',
        sites: [{ site: 'jobstreet', count: 1, jobs: [{ title: 'C', company: 'Z', url: 'u3', site: 'jobstreet' }] }],
      },
    ],
  };
  const template = '## {title}\n{company}';
  const { markdown, jobCount } = buildDigest(result, template);
  assert.equal(jobCount, 3);
  assert.equal(
    markdown,
    `# backend engineer\n\n## A\nX${JOB_SEPARATOR}## B\nY${JOB_SEPARATOR}# ai engineer\n\n## C\nZ\n`,
  );
  // send-digest splits on the separator; the blank line before --- keeps it a rule.
  assert.ok(!/\S\n---/.test(markdown));
});

test('an empty scrape yields an empty digest', () => {
  assert.deepEqual(buildDigest({ results: [{ keyword: 'x', sites: [] }] }, '## {title}'), {
    markdown: '',
    jobCount: 0,
  });
});

const summaryResult = (overrides = {}) => ({
  keywords: ['a', 'b'],
  requested_sites: ['glints', 'indeed', 'linkedin'],
  exit_code: 0,
  errors: [],
  results: [{ keyword: 'a', sites: [{ site: 'glints', jobs: [{}, {}] }, { site: 'indeed', jobs: [{}] }] }],
  ...overrides,
});
const NOW = new Date('2026-08-27T04:00:00Z');

test('summary: title and counts, no diagnostic when clean', () => {
  assert.equal(
    buildSummary(summaryResult(), { now: NOW }),
    '**Job digest — Thursday, 27 August 2026**\n\n_Scraped 3 jobs across 2 keyword(s) and 3 site(s). Errors: 0._',
  );
});

test('summary: bot version is carried when set', () => {
  assert.match(buildSummary(summaryResult(), { now: NOW, botVersion: 'v1.1.0' }), /3 site\(s\) \(bot v1\.1\.0\)\. Errors: 0\._$/);
});

test('summary: errors put a one-line diagnostic above the title', () => {
  const errors = Array.from({ length: 7 }, (_, i) => ({ keyword: 'a', site: `s${i}`, reason: 'fetch failed' }));
  const lines = buildSummary(summaryResult({ errors, exit_code: 1 }), { now: NOW }).split('\n');
  assert.equal(lines.length, 4);
  assert.match(lines[0], /^⚠️ 7 site\/keyword pair\(s\) failed \(scraper exit code 1\): s0\/a: fetch failed; .*; \+2 more$/);
  assert.equal(lines[1], '**Job digest — Thursday, 27 August 2026**');
  assert.match(lines[3], /Errors: 7\._$/);
});
