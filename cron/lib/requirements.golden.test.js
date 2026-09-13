// MONGO_URI=... npm run test:samples
//
// The extractor against real job-description outlines kept in MongoDB
// (requirement_samples, built by seeds/requirement_samples.runner.js). A sample with
// an `expected` field was labelled by hand: the heading a reader would expect and how
// each bullet should start, in order and with the exact count, at the default caps.
// Every sample, labelled or not, must render within those caps.
//
// Needs MONGO_URI and skips without it, as in CI. A failure here is a quality
// regression on a real posting, not a crash.

const { test } = require('node:test');
const assert = require('node:assert');

const { extractRequirements } = require('./requirements.js');

const MONGO_URI = process.env.MONGO_URI;
const DB_NAME = process.env.MONGO_DB_NAME || 'job-scraper';
const COLLECTION = 'requirement_samples';

async function loadSamples() {
  // Required lazily: mongodb is a dev dependency and the bot image omits it.
  const { MongoClient } = require('mongodb');
  const client = new MongoClient(MONGO_URI, { serverSelectionTimeoutMS: 15000 });
  await client.connect();
  try {
    return await client
      .db(DB_NAME)
      .collection(COLLECTION)
      .find({}, { projection: { requirements: 1, expected: 1 } })
      .sort({ _id: 1 })
      .toArray();
  } finally {
    await client.close();
  }
}

test(
  `requirement samples in ${DB_NAME}.${COLLECTION}`,
  { skip: MONGO_URI ? false : 'MONGO_URI is not set' },
  async (t) => {
    const samples = await loadSamples();
    const labelled = samples.filter((sample) => sample.expected);
    assert.ok(labelled.length > 0, `no labelled samples in ${DB_NAME}.${COLLECTION}; see seeds/requirement_samples.runner.js`);

    for (const sample of labelled) {
      await t.test(`golden: ${sample._id}`, () => {
        const { heading, items } = sample.expected;
        const actual = extractRequirements(sample.requirements);
        if (heading === null) {
          assert.equal(actual, null);
          return;
        }
        const shown = JSON.stringify(actual, null, 2);
        assert.ok(actual, 'expected a requirements block, got null');
        assert.equal(actual.heading, heading, shown);
        assert.equal(actual.items.length, items.length, shown);
        items.forEach((prefix, i) => {
          assert.ok(actual.items[i].startsWith(prefix), `item ${i} should start with ${JSON.stringify(prefix)}\n${shown}`);
        });
      });
    }

    await t.test(`all ${samples.length} samples render within the default caps`, () => {
      for (const sample of samples) {
        const actual = extractRequirements(sample.requirements);
        if (!actual) continue;
        assert.ok(['Kualifikasi', 'Ringkasan'].includes(actual.heading), sample._id);
        assert.ok(actual.items.length >= 1 && actual.items.length <= 5, `${sample._id}: ${actual.items.length} items`);
        for (const item of actual.items) {
          assert.ok([...item].length <= 80, `${sample._id}: over 80 chars: ${item}`);
          assert.ok(!/^[-•*·]\s/.test(item), `${sample._id}: bullet glyph left in: ${item}`);
          assert.ok(!/[\x00-\x08]/.test(item), `${sample._id}: control character in: ${item}`);
        }
      }
    });
  },
);
