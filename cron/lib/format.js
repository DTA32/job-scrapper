// Renders a scrape_jobs result into the digest file and its Discord message body.
//
// This is everything the bot prompt used to ask the model to do by hand, minus
// the requirements bullets (see lib/requirements.js): template substitution with
// the null rules, WIB date formatting, digest assembly and the summary lines.

const { JOB_SEPARATOR } = require('../send-digest.js');

const WIB = 'Asia/Jakarta';
const PLACEHOLDER = /\{([a-z_]+)\}/g;
const BARE_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_DATETIME =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/i;
// A static template line that heads a section, e.g. `**Details**` or `### Notes`.
const SECTION_HEADER = /^\s*(\*\*[^*]+\*\*:?|#{1,6}\s+\S.*)\s*$/;
const MAX_DIAGNOSTIC_ERRORS = 5;

const formatters = new Map();

function weekdayDate(date, timeZone) {
  if (!formatters.has(timeZone)) {
    formatters.set(
      timeZone,
      new Intl.DateTimeFormat('en-GB', {
        timeZone,
        weekday: 'long',
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      }),
    );
  }
  const parts = {};
  for (const { type, value } of formatters.get(timeZone).formatToParts(date)) parts[type] = value;
  return `${parts.weekday}, ${parts.day} ${parts.month} ${parts.year}`;
}

/** `Weekday, DD Month YYYY` for an instant, as seen in WIB. */
function formatWibDate(date = new Date()) {
  return weekdayDate(date, WIB);
}

/** A calendar date that is already local (WIB); null when it is not a real date. */
function formatCalendarDate(year, month, day) {
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return weekdayDate(date, 'UTC');
}

/**
 * Normalize a `posted_date` to `Weekday, DD Month YYYY`.
 *
 * Timestamps with a zone are converted to WIB first, so the date matches the
 * reader's local day. Bare dates and zone-less timestamps are taken as already
 * WIB and are not shifted. Anything unparseable passes through unchanged.
 */
function formatPostedDate(value) {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();

  let match = BARE_DATE.exec(trimmed);
  if (match) return formatCalendarDate(+match[1], +match[2], +match[3]) ?? value;

  match = ISO_DATETIME.exec(trimmed);
  if (!match) return value;
  if (!match[7]) return formatCalendarDate(+match[1], +match[2], +match[3]) ?? value;

  const iso = trimmed.replace(' ', 'T').replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? value : formatWibDate(new Date(ms));
}

const hasValue = (v) => v !== null && v !== undefined && String(v).trim() !== '';
const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Substitute one template line. Returns {text, dynamic, dropped}. */
function renderLine(line, values) {
  const names = [...line.matchAll(PLACEHOLDER)].map((m) => m[1]);
  if (names.length === 0) return { text: line, dynamic: false, dropped: false };
  if (!names.some((name) => hasValue(values[name]))) {
    return { text: line, dynamic: true, dropped: true };
  }

  // Drop each missing placeholder together with the separator it leaves dangling,
  // so `{company} | {location}` still renders the company when location is null.
  let text = line;
  for (const name of names) {
    if (hasValue(values[name])) continue;
    const token = escapeRegExp(`{${name}}`);
    const patterns = [
      new RegExp(`\\s*[|,]\\s*${token}`),
      new RegExp(`${token}\\s*[|,]\\s*`),
      new RegExp(`\\s*:\\s*${token}\\s*$`),
      new RegExp(token),
    ];
    const hit = patterns.find((pattern) => pattern.test(text));
    text = text.replace(hit, '');
  }

  // One pass, so a value that happens to contain `{field}` is never re-expanded.
  text = text.replace(PLACEHOLDER, (whole, name) =>
    hasValue(values[name]) ? String(values[name]).trim() : whole,
  );
  return { text, dynamic: true, dropped: false };
}

/** A section header whose whole body was dropped goes too, rather than heading nothing. */
function dropOrphanHeaders(lines) {
  lines.forEach((line, i) => {
    if (line.dynamic || !SECTION_HEADER.test(line.text)) return;
    const body = [];
    for (let j = i + 1; j < lines.length; j++) {
      const next = lines[j];
      if (!next.dynamic && (next.text.trim() === '' || SECTION_HEADER.test(next.text))) break;
      body.push(next);
    }
    if (body.some((b) => b.dynamic) && body.every((b) => b.dropped)) line.dropped = true;
  });
}

/** Collapse runs of blank lines and trim blank lines at either end. */
function tidy(texts) {
  const out = [];
  for (const text of texts) {
    const blank = text.trim() === '';
    if (blank && (out.length === 0 || out[out.length - 1].trim() === '')) continue;
    out.push(blank ? '' : text);
  }
  while (out.length && out[out.length - 1] === '') out.pop();
  return out.join('\n');
}

/**
 * Render one job through the template.
 *
 * `renderRequirements(outline)` turns the raw `requirements` outline into the
 * block that replaces `{requirements}` (heading line + bullets), or null to drop it.
 */
function renderJob(template, job, { renderRequirements } = {}) {
  const values = {
    ...job,
    posted_date: formatPostedDate(job.posted_date),
    requirements: renderRequirements ? renderRequirements(job.requirements) : job.requirements,
  };
  const lines = template.replace(/\r\n/g, '\n').split('\n').map((line) => renderLine(line, values));
  dropOrphanHeaders(lines);
  return tidy(lines.filter((line) => !line.dropped).map((line) => line.text));
}

/**
 * Assemble the digest file: one `# <keyword>` section per keyword with jobs, every
 * block separated by JOB_SEPARATOR (send-digest.js splits oversized digests there).
 * Returns {markdown, jobCount}; markdown is '' when there are no jobs.
 */
function buildDigest(result, template, options = {}) {
  const sections = [];
  let jobCount = 0;
  for (const keywordResult of result.results || []) {
    const blocks = [];
    for (const site of keywordResult.sites || []) {
      for (const job of Array.isArray(site && site.jobs) ? site.jobs : []) {
        blocks.push(renderJob(template, job, options));
      }
    }
    if (blocks.length === 0) continue;
    jobCount += blocks.length;
    sections.push(`# ${keywordResult.keyword}\n\n${blocks.join(JOB_SEPARATOR)}`);
  }
  return { markdown: sections.length ? `${sections.join(JOB_SEPARATOR)}\n` : '', jobCount };
}

function countJobs(result) {
  let total = 0;
  for (const keywordResult of result.results || []) {
    for (const site of keywordResult.sites || []) {
      total += Array.isArray(site && site.jobs) ? site.jobs.length : 0;
    }
  }
  return total;
}

/** One line flagging a non-zero exit or per-site errors; null when the scrape was clean. */
function buildDiagnostic(result) {
  const errors = Array.isArray(result.errors) ? result.errors : [];
  const exitCode = result.exit_code;
  const badExit = exitCode !== undefined && exitCode !== null && exitCode !== 0;
  if (!badExit && errors.length === 0) return null;

  const exitNote = badExit ? ` (scraper exit code ${exitCode})` : '';
  if (errors.length === 0) return `⚠️ Scrape finished with problems${exitNote}.`;

  const listed = errors
    .slice(0, MAX_DIAGNOSTIC_ERRORS)
    .map((e) => `${e.site}/${e.keyword}: ${e.reason}`)
    .join('; ');
  const more = errors.length > MAX_DIAGNOSTIC_ERRORS ? `; +${errors.length - MAX_DIAGNOSTIC_ERRORS} more` : '';
  return `⚠️ ${errors.length} site/keyword pair(s) failed${exitNote}: ${listed}${more}`;
}

/** The Discord message body: optional diagnostic, bold title, italic summary. */
function buildSummary(result, { now = new Date(), botVersion } = {}) {
  const keywords = Array.isArray(result.keywords) ? result.keywords.length : 0;
  const sites = Array.isArray(result.requested_sites) ? result.requested_sites.length : 0;
  const errors = Array.isArray(result.errors) ? result.errors.length : 0;
  const version = botVersion ? ` (bot ${botVersion})` : '';
  const lines = [
    `**Job digest — ${formatWibDate(now)}**`,
    '',
    `_Scraped ${countJobs(result)} jobs across ${keywords} keyword(s) and ${sites} site(s)${version}. Errors: ${errors}._`,
  ];
  const diagnostic = buildDiagnostic(result);
  return (diagnostic ? [diagnostic, ...lines] : lines).join('\n');
}

module.exports = {
  buildDiagnostic,
  buildDigest,
  buildSummary,
  countJobs,
  formatPostedDate,
  formatWibDate,
  renderJob,
};
