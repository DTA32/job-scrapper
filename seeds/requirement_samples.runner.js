#!/usr/bin/env node
// Builds the requirement_samples collection: real job-description outlines that the
// bot's requirements extractor is checked against (cron/lib/requirements.golden.test.js).
//
//   node seeds/requirement_samples.runner.js harvest [--dry-run]
//     Copies every job outline out of scrape_runs written by an MCP server that emits
//     outline text (run_metadata.requirements_format = "outline-v1"). Older runs hold
//     flattened or 600-char-window text and are skipped. Safe to re-run: one sample
//     per posting, refreshed from the newest run.
//
//   node seeds/requirement_samples.runner.js import <scraper output_dir> [--labels <file>] [--dry-run]
//     Adds the outlines from a local scrape (`python -m scraper -c <config>`),
//     optionally with hand labels from a JSON file of
//     {cases: [{fixture: "<site>-<first 12 hex of sha1(url)>.txt", heading, items}]}.
//
// A sample that carries a hand label (`expected`) keeps the text it was labelled
// against: harvest and unlabelled imports never rewrite it.
//
// Label a sample in mongosh:
//   db.requirement_samples.updateOne({ _id: "<id>" }, { $set: {
//     expected: { heading: "Kualifikasi", items: ["Minimal S1", "Pengalaman 2 tahun"] },
//     labelled_at: new Date().toISOString() } })
// `heading` is "Kualifikasi", "Ringkasan" or null; each item is how that bullet starts.
//
// Env: MONGO_URI (required), MONGO_DB_NAME (default job-scraper).

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { MongoClient } = require('mongodb');

const DB_NAME = process.env.MONGO_DB_NAME || 'job-scraper';
const COLLECTION = 'requirement_samples';
const OUTLINE_FORMAT = 'outline-v1';
const BATCH_SIZE = 500;

const sha1 = (text) => crypto.createHash('sha1').update(String(text)).digest('hex');
const hasOutline = (job) => typeof job.requirements === 'string' && job.requirements.trim() !== '';

/** One sample per posting, whichever run or keyword saw it. */
function sampleId(job) {
  return `${job.site}:${sha1(job.url || job.job_id || `${job.title}|${job.company}`)}`;
}

/** The name the old fixture files used for a posting ("<site>-<12 hex>.txt"); labels files key on it. */
function fixtureName(job) {
  const ident = String(job.job_id || '') || sha1(job.url);
  return `${job.site}-${ident.replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 12).replace(/^-+|-+$/g, '')}.txt`;
}

function sampleFields(job, keyword) {
  return {
    site: job.site,
    url: job.url || null,
    title: job.title || null,
    company: job.company || null,
    keyword: job.matched_keyword || keyword || null,
    requirements: job.requirements,
    format: OUTLINE_FORMAT,
  };
}

const upsert = (id, set, onInsert) => ({
  updateOne: { filter: { _id: id }, update: { $set: set, $setOnInsert: onInsert }, upsert: true },
});

async function labelledIds(collection) {
  const docs = await collection.find({ expected: { $exists: true } }, { projection: { _id: 1 } }).toArray();
  return new Set(docs.map((doc) => doc._id));
}

async function harvest(db, collection) {
  const labelled = await labelledIds(collection);
  const runs = db.collection('scrape_runs');
  const totalRuns = await runs.countDocuments({});
  const cursor = runs
    .find(
      { 'run_metadata.requirements_format': OUTLINE_FORMAT },
      { projection: { filtered_results: 1, raw_results: 1, _created_at: 1 } },
    )
    .sort({ _created_at: 1 });

  // Runs arrive oldest first: each posting keeps its first sighting's date and the
  // newest run's text, and gets exactly one upsert.
  const latest = new Map();
  const postings = new Set();
  let outlineRuns = 0;
  let kept = 0;
  for await (const run of cursor) {
    outlineRuns += 1;
    for (const key of ['filtered_results', 'raw_results']) {
      for (const entry of run[key] || []) {
        for (const raw of (entry.payload && entry.payload.jobs) || []) {
          if (!hasOutline(raw)) continue;
          const job = { site: entry.site, ...raw };
          const id = sampleId(job);
          postings.add(id);
          if (labelled.has(id)) {
            kept += 1;
            continue;
          }
          latest.set(id, {
            firstSeen: latest.has(id) ? latest.get(id).firstSeen : run._created_at,
            set: { ...sampleFields(job, entry.keyword), last_seen_at: run._created_at, last_run_id: run._id },
          });
        }
      }
    }
  }
  const ops = [...latest].map(([id, { firstSeen, set }]) =>
    upsert(id, set, { first_seen_at: firstSeen, source: 'scrape_run' }),
  );
  console.log(
    `[samples] scrape_runs: ${outlineRuns} of ${totalRuns} run(s) carry outline requirements -> ` +
      `${postings.size} posting(s); ${kept} outline(s) skipped to keep labelled text`,
  );
  return ops;
}

function importOutputDir(outputDir, labelsPath, labelled) {
  const labels = new Map();
  if (labelsPath) {
    for (const entry of JSON.parse(fs.readFileSync(labelsPath, 'utf8')).cases) labels.set(entry.fixture, entry);
  }
  const now = new Date().toISOString();
  const byId = new Map();
  const applied = new Set();
  let outlines = 0;
  for (const dir of fs.readdirSync(outputDir, { withFileTypes: true }).filter((d) => d.isDirectory())) {
    const files = fs.readdirSync(path.join(outputDir, dir.name)).filter((f) => f.endsWith('.json') && !f.endsWith('.raw.json'));
    for (const file of files) {
      const payload = JSON.parse(fs.readFileSync(path.join(outputDir, dir.name, file), 'utf8'));
      for (const job of payload.jobs || []) {
        if (!hasOutline(job)) continue;
        outlines += 1;
        const id = sampleId(job);
        const label = labels.get(fixtureName(job));
        if (labelled.has(id) && !label) continue;
        const set = { ...sampleFields(job, payload.keyword), last_seen_at: now };
        if (label) {
          set.expected = { heading: label.heading, items: label.items };
          set.labelled_at = now;
          set.label_source = path.basename(labelsPath);
          applied.add(label.fixture);
        }
        byId.set(id, { ...byId.get(id), ...set });
      }
    }
  }
  const ops = [...byId].map(([id, set]) => upsert(id, set, { first_seen_at: now, source: 'scraper_output' }));
  const unmatched = [...labels.keys()].filter((name) => !applied.has(name));
  if (unmatched.length) throw new Error(`labels with no matching job in ${outputDir}: ${unmatched.join(', ')}`);
  console.log(`[samples] ${outputDir}: ${outlines} job outline(s); labels applied ${applied.size}/${labels.size}`);
  return ops;
}

async function write(collection, ops, dryRun) {
  if (dryRun) {
    console.log(`[samples] dry run: ${ops.length} upsert(s) not written`);
    return;
  }
  let inserted = 0;
  let updated = 0;
  for (let i = 0; i < ops.length; i += BATCH_SIZE) {
    const result = await collection.bulkWrite(ops.slice(i, i + BATCH_SIZE), { ordered: true });
    inserted += result.upsertedCount;
    updated += result.modifiedCount;
  }
  await collection.createIndex({ site: 1 });
  await collection.createIndex({ 'expected.heading': 1 }, { sparse: true });
  console.log(`[samples] wrote ${inserted} new and ${updated} updated sample(s)`);
}

function parseArgs(argv) {
  const [command = 'harvest', ...rest] = argv;
  const options = { command, dryRun: false, labelsPath: null, positional: [] };
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--dry-run') options.dryRun = true;
    else if (rest[i] === '--labels') options.labelsPath = rest[++i];
    else options.positional.push(rest[i]);
  }
  return options;
}

async function main(argv) {
  const options = parseArgs(argv);
  if (!['harvest', 'import'].includes(options.command) || (options.command === 'import' && !options.positional[0])) {
    throw new Error('usage: requirement_samples.runner.js harvest [--dry-run] | import <output_dir> [--labels <file>] [--dry-run]');
  }
  if (!process.env.MONGO_URI) throw new Error('MONGO_URI env var required');

  const client = new MongoClient(process.env.MONGO_URI, { serverSelectionTimeoutMS: 15000 });
  await client.connect();
  try {
    const db = client.db(DB_NAME);
    const collection = db.collection(COLLECTION);
    console.log(`[samples] ${options.command} into ${DB_NAME}.${COLLECTION}${options.dryRun ? ' (dry run)' : ''}`);
    const ops =
      options.command === 'harvest'
        ? await harvest(db, collection)
        : importOutputDir(options.positional[0], options.labelsPath, await labelledIds(collection));
    await write(collection, ops, options.dryRun);
    const [total, labelled] = await Promise.all([
      collection.countDocuments({}),
      collection.countDocuments({ expected: { $exists: true } }),
    ]);
    console.log(`[samples] ${DB_NAME}.${COLLECTION}: ${total} sample(s), ${labelled} labelled`);
  } finally {
    await client.close();
  }
}

if (require.main === module) {
  main(process.argv.slice(2)).catch((err) => {
    console.error(`[samples] ${err.message}`);
    process.exit(1);
  });
}

module.exports = { fixtureName, sampleId };
