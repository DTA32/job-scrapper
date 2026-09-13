// Picks the bullets for a job's requirements block from its description outline.
//
// The scraper sends `requirements` as outline text (scraper/sites/_text.py): `## `
// heading lines, `- ` list items, blank lines between paragraphs. This finds the
// candidate-facing section by its heading and renders a few short bullets:
//
//   **Kualifikasi**  items from the qualifications section(s), in document order
//   **Ringkasan**    no qualifications section: the duties, or failing that the
//                    first substantive lines, so duties are never labelled as
//                    qualifications
//   (nothing)        only company blurb, benefits or application instructions
//
// Headings are classified by their own words, so a sentence that merely mentions
// "requirements" inside the duties never opens a section.

const DEFAULT_MAX_ITEMS = 5;
const DEFAULT_MAX_ITEM_CHARS = 80;

// Phrases are matched as whole words against a lowercased, punctuation-free
// heading ("What We’re Looking For:" -> "what we are looking for").
const VOCABULARY = {
  qualifications: [
    'requirement', 'requirements', 'required', 'qualification', 'qualifications',
    'kualifikasi', 'persyaratan', 'syarat', 'syarat pelamar', 'kriteria', 'criteria',
    'what we are looking for', 'who we are looking for', 'what we look for', 'looking for',
    'we need', 'what we need', 'we want', 'who we want', 'what you need', 'what you will need',
    'you will need', 'what you bring', 'you bring', 'you have', 'you should have', 'what you have',
    'what it takes', 'you need', 'need to have', 'to thrive', 'to succeed', 'mandatory belongings',
    'who you are', 'about you', 'your profile', 'candidate profile',
    'profil kandidat', 'ideal candidate', 'kandidat ideal', 'yang kami cari', 'kami mencari',
    'your background', 'educational background', 'latar belakang pendidikan',
    'skill', 'skills', 'skillset', 'skill set', 'hard skills', 'soft skills', 'technical skills',
    'knowledge', 'attributes', 'keahlian', 'kemampuan', 'kompetensi', 'competency', 'competencies',
    'certification', 'certifications', 'sertifikasi',
    'must have', 'must haves', 'nice to have', 'nice to haves', 'good to have', 'nilai tambah',
    'nilai plus', 'poin plus', 'diutamakan', 'preferred', 'bonus points', 'plus points', 'a plus',
    'advantage', 'advantages', 'experience', 'pengalaman', 'education', 'pendidikan',
    'tech stack', 'language', 'languages', 'bahasa',
    'exigences', 'compétences', 'compétences recherchées', 'profil recherché',
  ],
  responsibilities: [
    'responsibility', 'responsibilities', 'tanggung jawab', 'tugas', 'tugas utama', 'uraian tugas',
    'rincian tugas', 'deskripsi pekerjaan', 'deskripsi tugas', 'rincian pekerjaan',
    'job description', 'job descriptions', 'jobdesc', 'job desc', 'description', 'deskripsi',
    'job details', 'job scope', 'what you will do', 'what you do', 'what you will be doing',
    'what will you do', 'what you will own', 'you will own', 'how you will do it',
    'your role', 'the role', 'about the role', 'about this role', 'about the job',
    'about the position', 'get to know the role', 'in this role', 'the opportunity',
    'role overview', 'job overview', 'position overview', 'job summary', 'role summary',
    'position summary', 'duties', 'key duties', 'tasks', 'key areas of focus', 'areas of focus',
    'focus areas', 'what success looks like', 'your impact', 'your day', 'a day in the life',
    'day to day', 'your mission', 'scope', 'ruang lingkup', 'lingkup pekerjaan',
    'accountabilities', 'key accountabilities', 'tâches', 'missions',
  ],
  benefits: [
    'benefit', 'benefits', 'tunjangan', 'fasilitas', 'facilities', 'perks', 'perk',
    'what we offer', 'we offer', 'what we can offer', 'we can offer', 'company offers',
    'what you will get', 'what you get', 'you will get', 'why join', 'why join us', 'why us',
    'compensation', 'kompensasi', 'keuntungan', 'bonus', 'insentif', 'incentive', 'incentives',
    'salary and benefits', 'whats in it for you', 'rewards', 'kesejahteraan', 'job highlights',
  ],
  about: [
    'about us', 'about the company', 'about company', 'company overview', 'company profile',
    'company description', 'company background', 'who we are', 'tentang kami',
    'tentang perusahaan', 'profil perusahaan', 'our company', 'our story', 'our mission',
    'our vision', 'our culture', 'visi', 'misi', 'the company', 'about team', 'about the team',
    'get to know the team', 'get to know our team', 'life at', 'what we value', 'our values',
    'what we stand for', 'operating principles', 'equal opportunity', 'equal opportunity employer',
    'our workplace',
  ],
  apply: [
    'how to apply', 'cara melamar', 'cara mendaftar', 'cara daftar', 'apply now', 'to apply',
    'application', 'application process', 'application questions', 'in your application',
    'recruitment process', 'proses rekrutmen', 'interview process', 'hiring process',
    'selection process', 'proses seleksi', 'kirim cv', 'send your cv', 'contact', 'kontak',
    'hubungi', 'postuler',
  ],
  info: [
    'location', 'lokasi', 'penempatan', 'placement', 'work location', 'workplace type',
    'working hours', 'jam kerja', 'hari kerja', 'working days', 'work schedule', 'jadwal kerja',
    'salary', 'gaji', 'employment type', 'job type', 'tipe pekerjaan', 'status karyawan',
    'contract', 'kontrak', 'work arrangement', 'work mode', 'industry', 'industri', 'deadline',
    'closing date', 'additional information', 'job category', 'job family', 'job family group',
    'requisition id', 'reference', 'référence', 'localisation', 'durée', 'disclaimer',
    'this role is not for',
  ],
};
const OTHER_KINDS = ['responsibilities', 'benefits', 'about', 'apply', 'info'];
// Kinds never used for a Ringkasan: they describe the company, not the job.
const NOT_SUMMARY = new Set(['about', 'benefits', 'apply', 'info']);
// Labels that open a section inline, as in "Requirements: Go, SQL".
const SECTION_LABELS = new Set([
  'requirement', 'requirements', 'qualification', 'qualifications', 'kualifikasi',
  'persyaratan', 'syarat', 'responsibilities', 'tanggung jawab', 'job description',
  'deskripsi pekerjaan', 'benefit', 'benefits', 'tunjangan', 'fasilitas',
]);
// Words a plain-text heading may carry around its vocabulary ("Job Requirements").
const HEADING_FILLER = new Set([
  'job', 'key', 'main', 'your', 'our', 'the', 'a', 'an', 'and', 'dan', 'or', 'atau', 'of',
  'for', 'to', 'di', 'untuk', 'yang', 'general', 'umum', 'khusus', 'utama', 'basic',
  'minimum', 'minimal', 'additional', 'tambahan', 'other', 'lainnya', 'wajib',
  'dibutuhkan', 'diperlukan', 'position', 'posisi', 'role', 'this', 'kami', 'kamu', 'anda',
]);

const EMOJI = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{FE0F}\u{200D}\u{20E3}]/gu;
const LEADING_MARKS = /^(?:[\s\-–—•·●○◦▪■□►▶➢➤✓✔☑❖◆◇★☆*»>→#]+|\(?\d{1,2}[.)]\s+|\(?[a-z][.)]\s+)/u;
// A prose paragraph opening like this is a qualifications section without a heading.
const QUALIFICATION_LEAD =
  /^(kami mencari kandidat|kandidat (yang|ideal|harus)|calon kandidat|pelamar (harus|wajib)|we are looking for (someone|a candidate|candidates|people|an individual|individuals)|the ideal candidate|ideal candidates?|the successful candidate|successful candidates?|candidates? (must|should|will need|need to)|you (have|bring|should have|will need|must have)|to be successful|requirements (include|are)|qualifications (include|are))( |$)/;
const INLINE_LABEL = /^([^:：]{3,40})[:：]\s+(\S.*)$/;
const LINK_OR_EMAIL = /(https?:\/\/\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+)/gi;
const HAS_LINK_OR_EMAIL = new RegExp(LINK_OR_EMAIL.source, 'i');
const CALL_TO_ACTION =
  /\b(apply now|apply here|apply via|click (here|the link)|kirim (cv|lamaran)|send (your )?(cv|resume)|lamar sekarang|segera lamar|daftar sekarang|only shortlisted|hanya kandidat|submit your (cv|resume|application)|apply today|we invite you to apply|mari bergabung|bergabung(lah)? bersama kami|kami menyambut)\b/i;
const COMPANY_BLURB =
  /\b(is a leading|is one of the|we are a|founded in|didirikan|(merupakan|adalah) (sebuah )?(perusahaan|agensi|agency|startup|platform|usaha)|perusahaan yang bergerak|headquartered|berkantor pusat|is a fast[- ]growing|our mission|our vision|kami adalah|established in|sejak tahun)\b/i;
// Wording that marks a line or sentence as a requirement without any heading:
// candidate traits at the start, years of experience, degrees, "is a plus", "kandidat harus".
const QUALIFICATION_CUE = new RegExp(
  [
    String.raw`^(at least|minimum|min\.|minimal|pendidikan|pengalaman|memiliki|menguasai|mampu|bersedia|bisa|sehat|jujur|usia|pria|wanita|laki|lulusan|fresh graduate|bachelor|master|diploma|degree|experience (with|in|using|working)|experienced (in|with|using)|proficien|familiar|knowledge of|understanding of|strong (knowledge|understanding|background|experience|command|communication|skills?)|good (knowledge|understanding|command|communication)|excellent (communication|command)|able to|ability to|fluent|fluency)\b`,
    String.raw`\b\d+(\s*[-–]\s*\d+)?\+?\s*(years?|yrs?|tahun)\b`,
    String.raw`\b(bachelor|master)[’']?s? degree\b|\bdegree in\b|\bgelar (sarjana|s1|s2)\b|\b(d3|s1|s2)\b`,
    String.raw`\bis a (plus|must)\b|\bare a plus\b|\b(is|are) required\b|\bnilai (tambah|plus)\b|\bdiutamakan\b|\bsangat penting untuk posisi\b`,
    String.raw`\b(kandidat|pelamar|candidates?|applicants?) (harus|wajib|diharapkan|must|should|will need)\b|\b(harus|wajib) memiliki\b`,
    String.raw`^[\w/&-]+(\s[\w/&-]+){0,3}\s(is\s)?(required|wajib|a must)[.!]?$`,
  ].join('|'),
  'u',
);
// Logistics and perks that employers list among the requirements ("Lokasi Depo ...", "Disediakan Mess").
const INFO_ITEM = /^(lokasi|location|penempatan|placement|disediakan|tersedia|provided|benefits?|gaji|salary|mess)\b/i;
const ABBREVIATIONS = new Set([
  'e.g', 'i.e', 'etc', 'min', 'max', 'no', 'dr', 'mr', 'mrs', 'ms', 'pt', 'tbk', 'jl', 'inc',
  'ltd', 'co', 'vs', 'approx', 'dll', 'dsb', 'dst', 'sr', 'jr', 'st', 'yrs', 'exp', 'u.s',
]);

function normalizeWords(text) {
  return String(text)
    .toLowerCase()
    .replace(EMOJI, ' ')
    .replace(/[’‘`´]/g, "'")
    .replace(/\b(you|we|they|i)'re\b/g, '$1 are')
    .replace(/\b(you|we|they|i)'ll\b/g, '$1 will')
    .replace(/\b(you|we|they|i)'ve\b/g, '$1 have')
    .replace(/'/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

// Phrase lists, normalized the same way as headings, and indexed by first word.
const PHRASES = Object.fromEntries(
  Object.entries(VOCABULARY).map(([kind, list]) => [kind, list.map(normalizeWords)]),
);
// Duty words that make a qualifications heading "mixed", like "Tâches et compétences
// recherchées": its list is usually the duties, so a pure requirements section wins.
const DUTY_PHRASES = [
  'responsibility', 'responsibilities', 'tanggung jawab', 'tugas', 'duties', 'tasks', 'tâches',
  'job description', 'job descriptions', 'deskripsi pekerjaan', 'what you will do',
].map(normalizeWords);
const PHRASES_BY_FIRST_WORD = new Map();
for (const phrase of Object.values(PHRASES).flat()) {
  const words = phrase.split(' ');
  const bucket = PHRASES_BY_FIRST_WORD.get(words[0]) || [];
  bucket.push(words);
  PHRASES_BY_FIRST_WORD.set(words[0], bucket.sort((a, b) => b.length - a.length));
}

/** The section kind a heading names, or null when its words name none. */
function classifyHeading(text) {
  const normalized = normalizeWords(text);
  if (!normalized) return null;
  const padded = ` ${normalized} `;
  const has = (phrase) => padded.includes(` ${phrase} `);

  // Qualifications win outright: "Requirements & Responsibilities" holds the requirements.
  if (PHRASES.qualifications.some(has)) return 'qualifications';

  // Otherwise the most specific phrase wins: "Company Description" is about the
  // company even though "description" alone would mean the duties.
  let best = null;
  for (const kind of OTHER_KINDS) {
    for (const phrase of PHRASES[kind]) {
      if (has(phrase) && (!best || phrase.length > best.length)) best = { kind, length: phrase.length };
    }
  }
  if (best) return best.kind;
  if (/^why /.test(normalized)) return 'benefits';
  return /^(about|tentang) /.test(normalized) ? 'about' : null;
}

function isMixedHeading(text) {
  const padded = ` ${normalizeWords(text)} `;
  const has = (phrase) => padded.includes(` ${phrase} `);
  return PHRASES.qualifications.some(has) && DUTY_PHRASES.some(has);
}

/** True when a plain line is nothing but vocabulary and filler words ("Job Requirements"). */
function isVocabularyOnly(text) {
  const words = normalizeWords(text).split(' ').filter(Boolean);
  let i = 0;
  let matched = false;
  while (i < words.length) {
    const phrase = (PHRASES_BY_FIRST_WORD.get(words[i]) || []).find((candidate) =>
      candidate.every((word, k) => words[i + k] === word),
    );
    if (phrase) {
      i += phrase.length;
      matched = true;
    } else if (HEADING_FILLER.has(words[i])) {
      i += 1;
    } else {
      return false;
    }
  }
  return matched;
}

/** A plain-text line that reads as a heading. Outline `## ` lines never need this. */
function looksLikeHeading(line) {
  if (line.startsWith('- ') || line.length > 80) return false;
  const words = line.split(/\s+/).length;
  if (/[:：]$/.test(line)) return words <= 12;
  if (/[.!?;,]$/.test(line) || words > 6) return false;
  return isVocabularyOnly(line);
}

function isSectionLabel(label) {
  const normalized = normalizeWords(label);
  return SECTION_LABELS.has(normalized) || SECTION_LABELS.has(normalized.replace(/^(job|key|main) /, ''));
}

/** Split an outline into blocks: {heading, kind, lines}. The first block may be headless. */
function splitBlocks(outline) {
  const blocks = [];
  let current = { heading: null, kind: null, lines: [] };
  const open = (heading, firstLine) => {
    blocks.push(current);
    const text = heading.replace(/[:：]\s*$/, '').trim();
    current = {
      heading: text,
      kind: classifyHeading(text),
      mixed: isMixedHeading(text),
      lines: firstLine ? [firstLine] : [],
    };
  };

  let paragraphStart = true;
  for (const raw of outline.split('\n')) {
    const line = raw.trim();
    if (!line) {
      if (current.resumeKind !== undefined) {
        // The headless qualifications paragraph ends here; the enclosing section resumes.
        blocks.push(current);
        current = { heading: null, kind: current.resumeKind, lines: [] };
      }
      current.lines.push('');
      paragraphStart = true;
      continue;
    }
    const startsParagraph = paragraphStart;
    paragraphStart = false;
    if (line.startsWith('## ')) {
      open(line.slice(3));
      paragraphStart = true;
      continue;
    }
    if (line.startsWith('- ')) {
      current.lines.push(line);
      continue;
    }
    if (looksLikeHeading(line)) {
      open(line);
      paragraphStart = true;
      continue;
    }
    if (startsParagraph && current.kind !== 'qualifications' && QUALIFICATION_LEAD.test(normalizeWords(line))) {
      blocks.push(current);
      current = { heading: null, kind: 'qualifications', lines: [line], resumeKind: current.kind };
      continue;
    }
    const inline = INLINE_LABEL.exec(line);
    if (inline && isSectionLabel(inline[1])) {
      open(inline[1], inline[2]);
      continue;
    }
    current.lines.push(line);
  }
  blocks.push(current);

  // An unrecognized heading right under a known one usually subdivides it ("Technical:"
  // under "Requirements") -- but only when its body is list-like, so a company-name
  // heading followed by a blurb does not turn into qualifications.
  for (let i = 1; i < blocks.length; i++) {
    const block = blocks[i];
    const previous = blocks[i - 1];
    if (block.heading === null || block.kind || !previous.kind) continue;
    const content = block.lines.filter(Boolean);
    if (content.some((l) => l.startsWith('- ')) || content.every((l) => l.length <= 120)) {
      block.kind = previous.kind;
    }
  }
  return blocks.filter((block) => block.heading !== null || block.lines.some(Boolean));
}

function sentences(text) {
  const out = [];
  let start = 0;
  const boundary = /[.!?]+(?=\s+["'(\[]?[\p{Lu}\d])/gu;
  let match;
  while ((match = boundary.exec(text))) {
    const lastWord = (/(\S+)$/.exec(text.slice(start, match.index)) || ['', ''])[1];
    const bare = lastWord.replace(/^[("'[]+/, '');
    // "e.g. Go", "Min. 2 years", "PT. Maju": a period that ends an abbreviation.
    if (match[0] === '.' && (ABBREVIATIONS.has(bare.toLowerCase()) || /^\p{Lu}$/u.test(bare))) continue;
    const end = match.index + match[0].length;
    out.push(text.slice(start, end).trim());
    start = end;
  }
  const tail = text.slice(start).trim();
  if (tail) out.push(tail);
  return out;
}

function isListLike(block) {
  const content = block.lines.filter(Boolean);
  return content.some((line) => line.startsWith('- ')) || (content.length >= 2 && content.every((line) => line.length <= 120));
}

/** Candidate items of a block: its list items, else its lines, else its sentences. */
function blockItems(block) {
  const lines = block.lines.filter(Boolean);
  const listed = lines.filter((line) => line.startsWith('- ')).map((line) => line.slice(2));
  if (listed.length) return listed;
  if (lines.length >= 2) return lines.flatMap((line) => (line.length > 120 ? sentences(line) : [line]));
  return sentences(lines.join(' '));
}

function cleanItem(text) {
  let item = text.replace(EMOJI, ' ');
  for (let previous = null; previous !== item; ) {
    previous = item;
    item = item.replace(LEADING_MARKS, '').trimStart();
  }
  return item.replace(/\s+/g, ' ').trim().replace(/[;,]+$/, '').trim();
}

function isNoise(item) {
  if (item.length < 2 || !/\p{L}/u.test(item)) return true;
  if (CALL_TO_ACTION.test(item)) return true;
  if (!HAS_LINK_OR_EMAIL.test(item)) return false;
  // Little more than a link or an address, e.g. "Email: hr@acme.com".
  const rest = normalizeWords(item.replace(LINK_OR_EMAIL, ' '));
  return rest.split(' ').filter(Boolean).length < 3;
}

const dedupeKey = (text) => normalizeWords(text).replace(/ /g, '');

function truncate(text, maxChars) {
  const chars = [...text];
  if (chars.length <= maxChars) return text;
  let cut = chars.slice(0, maxChars - 1).join('');
  const space = cut.lastIndexOf(' ');
  if (space >= Math.floor(maxChars * 0.6)) cut = cut.slice(0, space);
  return `${cut.replace(/[\s,;:(\-–—/]+$/, '')}…`;
}

function readsLikeRequirements(block) {
  const items = blockItems(block).map(cleanItem).filter((item) => !isNoise(item));
  const cued = items.filter((item) => QUALIFICATION_CUE.test(item.toLowerCase())).length;
  return cued >= 2 && cued >= items.length / 2;
}

function collectItems(blocks, { maxItems, maxItemChars, summary, only, bySentence }) {
  const items = [];
  const seen = new Set();
  for (const block of blocks) {
    const headingKey = block.heading ? dedupeKey(block.heading) : null;
    const candidates = bySentence ? block.lines.filter(Boolean).flatMap(sentences) : blockItems(block);
    for (const raw of candidates) {
      const item = cleanItem(raw);
      if (isNoise(item) || (summary ? COMPANY_BLURB.test(item) : INFO_ITEM.test(item))) continue;
      if (only && !only(item)) continue;
      const key = dedupeKey(item);
      if (!key || seen.has(key) || key === headingKey) continue;
      seen.add(key);
      items.push(truncate(item, maxItemChars));
      if (items.length >= maxItems) return items;
    }
  }
  return items;
}

/** {heading: 'Kualifikasi' | 'Ringkasan', items} for an outline, or null. */
function extractRequirements(outline, { maxItems = DEFAULT_MAX_ITEMS, maxItemChars = DEFAULT_MAX_ITEM_CHARS } = {}) {
  if (typeof outline !== 'string' || !outline.trim()) return null;
  const blocks = splitBlocks(outline);
  const limits = { maxItems, maxItemChars };

  // A listed section beats prose ("We are looking for an engineer who..." above the real
  // list), and a pure requirements heading beats one that also names the duties.
  const qualificationBlocks = blocks.filter((block) => block.kind === 'qualifications');
  const tiers = [
    (block) => !block.mixed && isListLike(block),
    (block) => block.mixed && isListLike(block),
    (block) => !block.mixed && !isListLike(block),
    (block) => block.mixed && !isListLike(block),
  ];
  for (const inTier of tiers) {
    const items = collectItems(qualificationBlocks.filter(inTier), { ...limits, summary: false });
    if (items.length) return { heading: 'Kualifikasi', items };
  }

  // No qualifications heading. A list that reads like requirements still is one, even
  // under a duties heading an employer copy-pasted ("0-2 years of experience", "... is a plus").
  const unheaded = blocks.filter((block) => block.kind !== 'qualifications' && !NOT_SUMMARY.has(block.kind));
  const cuedLists = unheaded.filter((block) => isListLike(block) && readsLikeRequirements(block));
  let found = collectItems(cuedLists, { ...limits, summary: false });
  if (found.length) return { heading: 'Kualifikasi', items: found };

  // Prose-only postings (Glints' generated descriptions): the sentences that state a requirement.
  const cued = (item) => QUALIFICATION_CUE.test(item.toLowerCase());
  found = collectItems(unheaded.filter((block) => !isListLike(block)), {
    ...limits,
    summary: false,
    only: cued,
    bySentence: true,
  });
  if (found.length) return { heading: 'Kualifikasi', items: found };

  // Otherwise summarize the duties, their list before any prose about the role.
  const duties = blocks.filter((block) => block.kind === 'responsibilities');
  for (const group of [duties.filter(isListLike), duties.filter((block) => !isListLike(block))]) {
    found = collectItems(group, { ...limits, summary: true });
    if (found.length) return { heading: 'Ringkasan', items: found };
  }

  const rest = collectItems(
    blocks.filter((block) => !NOT_SUMMARY.has(block.kind)),
    { ...limits, summary: true },
  );
  return rest.length ? { heading: 'Ringkasan', items: rest } : null;
}

/** The `{requirements}` block: a bold heading line, then one `• ` bullet per item. */
function renderRequirements(outline, options) {
  const extracted = extractRequirements(outline, options);
  if (!extracted) return null;
  return [`**${extracted.heading}**`, ...extracted.items.map((item) => `• ${item}`)].join('\n');
}

function optionsFromEnv(env = process.env) {
  const positive = (raw, fallback) => {
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  };
  return {
    maxItems: positive(env.REQ_MAX_ITEMS, DEFAULT_MAX_ITEMS),
    maxItemChars: positive(env.REQ_MAX_ITEM_CHARS, DEFAULT_MAX_ITEM_CHARS),
  };
}

module.exports = {
  classifyHeading,
  extractRequirements,
  optionsFromEnv,
  renderRequirements,
  splitBlocks,
};
