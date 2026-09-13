// node --test lib/requirements.test.js
const { test } = require('node:test');
const assert = require('node:assert');

const { classifyHeading, extractRequirements, optionsFromEnv, renderRequirements } = require('./requirements.js');

const items = (outline, options) => {
  const extracted = extractRequirements(outline, options);
  return extracted && [extracted.heading, extracted.items];
};

test('heading vocabulary: qualifications win, then the most specific phrase', () => {
  assert.equal(classifyHeading('Requirements & Responsibilities'), 'qualifications');
  assert.equal(classifyHeading('🔍 What We’re Looking For:'), 'qualifications');
  assert.equal(classifyHeading('Kualifikasi Umum'), 'qualifications');
  assert.equal(classifyHeading('About You'), 'qualifications');
  assert.equal(classifyHeading('About the Role'), 'responsibilities');
  assert.equal(classifyHeading('Company Description'), 'about');
  assert.equal(classifyHeading('About Tokopedia'), 'about');
  assert.equal(classifyHeading('What You Will Get'), 'benefits');
  assert.equal(classifyHeading('Cara Melamar'), 'apply');
  assert.equal(classifyHeading('Backend Engineer'), null);
});

test('headings seen in live descriptions classify as expected', () => {
  const expected = {
    "What you'll own": 'responsibilities',
    'Your main duties in flying with us': 'responsibilities',
    'Nilai Tambah': 'qualifications',
    'Knowledge, Skills and Attributes': 'qualifications',
    'Language': 'qualifications',
    'Exigences': 'qualifications',
    'What we can offer': 'benefits',
    'Why Voca': 'benefits',
    'Interview Process': 'apply',
    'This role is not for': 'info',
    'Get to know the team': 'about',
    'Our Operating Principles': 'about',
  };
  for (const [heading, kind] of Object.entries(expected)) assert.equal(classifyHeading(heading), kind, heading);
});

test('a prose paragraph that opens like a qualifications section counts as one', () => {
  const outline = [
    'PT GSI adalah perusahaan yang didirikan oleh PSSI.',
    '',
    'Sebagai AI Engineer, Anda akan merancang solusi AI. Anda juga bekerja dengan tim teknis.',
    '',
    'Kami mencari kandidat yang memiliki gelar S1 dan pengalaman 1 hingga 3 tahun. Kandidat harus menguasai Redis.',
    '',
    'Kirim CV Anda sekarang.',
  ].join('\n');
  assert.deepEqual(items(outline), [
    'Kualifikasi',
    ['Kami mencari kandidat yang memiliki gelar S1 dan pengalaman 1 hingga 3 tahun.', 'Kandidat harus menguasai Redis.'],
  ]);
});

test('a qualifications section wins over duties that come first', () => {
  const outline = '## Job Description\n- Build APIs\n\n## Qualifications\n- Go\n- SQL';
  assert.deepEqual(items(outline), ['Kualifikasi', ['Go', 'SQL']]);
});

test('several qualifications sections merge in document order up to the cap', () => {
  const outline = '## Must have\n- A skill\n- B skill\n## Responsibilities\n- Duty\n## Nice to have\n- C skill\n- D skill';
  assert.deepEqual(items(outline, { maxItems: 3 }), ['Kualifikasi', ['A skill', 'B skill', 'C skill']]);
});

test('"requirements" inside a duty never opens a section', () => {
  const outline = '## Responsibilities\n- Ensure the system meets the requirements of the client\n- Write tests';
  assert.deepEqual(items(outline), [
    'Ringkasan',
    ['Ensure the system meets the requirements of the client', 'Write tests'],
  ]);
});

test('plain-text headings: colon lines and vocabulary-only lines, not item lines', () => {
  assert.deepEqual(items('Kualifikasi:\n- S1 Informatika\n- 2 tahun pengalaman'), [
    'Kualifikasi',
    ['S1 Informatika', '2 tahun pengalaman'],
  ]);
  assert.deepEqual(items('Intro line.\nWhat We’re Looking For\nStrong Go skills\nExperience with SQL'), [
    'Kualifikasi',
    ['Strong Go skills', 'Experience with SQL'],
  ]);
});

test('an inline section label opens its section', () => {
  assert.deepEqual(items('We build logistics software.\nRequirements: Python, SQL and Docker.'), [
    'Kualifikasi',
    ['Python, SQL and Docker.'],
  ]);
});

test('an unrecognized sub-heading continues the section above it', () => {
  const outline = '## Requirements\n## Technical\n- Go\n## Soft\n- Communication';
  assert.deepEqual(items(outline), ['Kualifikasi', ['Go', 'Communication']]);
});

test('a company-name heading with a prose blurb is not folded into qualifications', () => {
  const outline =
    '## Requirements\n- Go\n## PT Maju Jaya\nPT Maju Jaya is a leading logistics company founded in 1990 with offices across Indonesia and a strong culture of ownership and care.';
  assert.deepEqual(items(outline), ['Kualifikasi', ['Go']]);
});

test('prose-only descriptions summarize without the company blurb', () => {
  const outline =
    'PT X is a leading fintech company. We are looking for a Backend Engineer to join our team. You will build scalable APIs.';
  assert.deepEqual(items(outline), [
    'Ringkasan',
    ['We are looking for a Backend Engineer to join our team.', 'You will build scalable APIs.'],
  ]);
});

test('sentence splitting keeps abbreviations together', () => {
  const outline = 'Min. 2 years with Go, e.g. Gin or Echo. Familiar with PT. Telkom systems. Fluent English.';
  assert.deepEqual(items(outline)[1], [
    'Min. 2 years with Go, e.g. Gin or Echo.',
    'Familiar with PT. Telkom systems.',
    'Fluent English.',
  ]);
});

test('only company, benefits and application text yields nothing', () => {
  const outline = '## About Us\nWe are a bank.\n## Benefits\n- Laptop\n## How to apply\n- Send your CV';
  assert.equal(extractRequirements(outline), null);
  assert.equal(renderRequirements(outline), null);
});

test('items are cleaned, deduplicated, and stripped of links and calls to action', () => {
  const outline = [
    '## Requirements',
    '- ✅ Python;',
    '- 1. SQL',
    '- python',
    '- Send your CV to hr@acme.com',
    '- https://acme.com/apply',
    '- Requirements',
  ].join('\n');
  assert.deepEqual(items(outline), ['Kualifikasi', ['Python', 'SQL']]);
});

test('long items are cut at a word boundary with an ellipsis', () => {
  const long = 'Minimal 3 tahun pengalaman sebagai Full Stack Developer dan/atau Mobile App Developer di startup';
  const [, [item]] = items(`## Kualifikasi\n- ${long}`);
  assert.ok([...item].length <= 80, item);
  assert.match(item, /\S…$/);
  assert.ok(long.startsWith(item.slice(0, -1)));
});

test('renderRequirements emits a bold heading and bullets', () => {
  assert.equal(renderRequirements('## Requirements\n- Go\n- SQL'), '**Kualifikasi**\n• Go\n• SQL');
  assert.equal(renderRequirements(null), null);
  assert.equal(renderRequirements('   '), null);
});

test('options come from REQ_MAX_ITEMS / REQ_MAX_ITEM_CHARS with safe fallbacks', () => {
  assert.deepEqual(optionsFromEnv({}), { maxItems: 5, maxItemChars: 80 });
  assert.deepEqual(optionsFromEnv({ REQ_MAX_ITEMS: '3', REQ_MAX_ITEM_CHARS: 'x' }), { maxItems: 3, maxItemChars: 80 });
});
