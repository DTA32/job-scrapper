// node --test lib/requirements.golden.test.js
//
// The extractor against real scraped outlines (cron/fixtures/requirements), with
// expectations labelled by hand from the text. A failure here is a quality
// regression on a real posting, not a crash. Refresh the corpus with
// scripts/dump_requirement_fixtures.py; label new cases in golden.json.

const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const { extractRequirements } = require('./requirements.js');

const FIXTURES = path.join(__dirname, '..', 'fixtures', 'requirements');
const golden = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'golden.json'), 'utf8'));
const read = (name) => fs.readFileSync(path.join(FIXTURES, name), 'utf8');

for (const expected of golden.cases) {
  test(`golden: ${expected.fixture}`, () => {
    const actual = extractRequirements(read(expected.fixture));
    if (expected.heading === null) {
      assert.equal(actual, null);
      return;
    }
    const shown = JSON.stringify(actual, null, 2);
    assert.ok(actual, 'expected a requirements block, got null');
    assert.equal(actual.heading, expected.heading, shown);
    assert.equal(actual.items.length, expected.items.length, shown);
    expected.items.forEach((prefix, i) => {
      assert.ok(actual.items[i].startsWith(prefix), `item ${i} should start with ${JSON.stringify(prefix)}\n${shown}`);
    });
  });
}

test('every fixture renders within the default caps', () => {
  const fixtures = fs.readdirSync(FIXTURES).filter((name) => name.endsWith('.txt'));
  assert.ok(fixtures.length >= 40, `expected a corpus of at least 40 fixtures, found ${fixtures.length}`);
  for (const name of fixtures) {
    const actual = extractRequirements(read(name));
    if (!actual) continue;
    assert.ok(['Kualifikasi', 'Ringkasan'].includes(actual.heading), name);
    assert.ok(actual.items.length >= 1 && actual.items.length <= 5, `${name}: ${actual.items.length} items`);
    for (const item of actual.items) {
      assert.ok([...item].length <= 80, `${name}: over 80 chars: ${item}`);
      assert.ok(!/^[-•*·]\s/.test(item), `${name}: bullet glyph left in: ${item}`);
      assert.ok(!/[\x00-\x08]/.test(item), `${name}: control character in: ${item}`);
    }
  }
});

test('every golden case points at a fixture that exists', () => {
  for (const { fixture } of golden.cases) assert.ok(fs.existsSync(path.join(FIXTURES, fixture)), fixture);
});
