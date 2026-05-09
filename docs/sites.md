# Sites

Per-site notes that affect what config is feasible. Read this before
proposing URL or filter changes.

## Coverage matrix

How reliably each canonical field gets populated, per site, on the typical
search result page (no detail-page fetch).

| Field             | jobstreet | glints | linkedin | indeed |
|-------------------|-----------|--------|----------|--------|
| `title`           | ✅        | ✅     | ✅       | ✅     |
| `company`         | ✅        | ✅     | ✅       | ✅     |
| `location`        | ✅        | ✅     | ✅       | ✅     |
| `url`             | ✅        | ✅     | ✅       | ✅     |
| `salary`          | partial   | partial| ❌       | partial|
| `posted_date`     | ✅ (id)   | ✅     | ✅       | ✅     |
| `posted_at`       | ✅        | ✅     | ✅       | ✅     |
| `work_type`       | partial   | ✅     | ❌       | ❌     |
| `employment_type` | partial   | ✅     | ❌       | ❌     |
| `experience_level`| ❌        | ✅     | ❌       | ❌     |
| `job_id`          | ✅        | ✅     | ✅       | ✅     |

**✅** = reliably populated. **partial** = sometimes populated when the
listing exposes it. **❌** = currently never populated by the parser.

Implication for filters: `work_type` and `employment_type` filters mostly
affect Glints. Other sites pass via the conservative null-rule.

## URL template recency params

Each site has its own server-side recency filter. Keep the URL param
aligned with `max_age_hours` to minimize wasted fetches.

| Site      | Param          | Format                      | Example for last 24h           |
|-----------|----------------|-----------------------------|--------------------------------|
| jobstreet | `daterange`    | days (integer)              | `?daterange=1`                 |
| linkedin  | `f_TPR`        | seconds, prefix `r`         | `&f_TPR=r86400` (24h)          |
| indeed    | `fromage`      | days (integer)              | `&fromage=1`                   |
| glints    | none           | n/a                         | client-side `max_age_hours` only |

Coupling: if you increase `max_age_hours`, also widen these URL params
(`daterange=7` for last week, `f_TPR=r604800`, `fromage=7`). Otherwise
the URL only returns the past day and the wider client window has nothing
extra to admit.

## Posted-date sources

How `posted_date` is extracted per site (relevant when debugging filter
behavior).

| Site      | Source                                              | Format example                    |
|-----------|-----------------------------------------------------|-----------------------------------|
| jobstreet | `__NEXT_DATA__` `listingDate`/`createdDate`         | `"2 hari yang lalu"` (Indonesian) |
| glints    | `__NEXT_DATA__` `publishedAt`/`createdAt`           | `"2026-04-22T02:44:52.044Z"`      |
| linkedin  | `<time class="job-search-card__listdate">` datetime | `"2026-05-09"` (ISO date)         |
| indeed    | embedded `mosaic-data` JSON `formattedRelativeTime` | `"5 hari yang lalu"` or `"Baru dipasang"` |

`posted_at` is the parsed ISO UTC equivalent. For Indeed, it comes directly
from `pubDate` (epoch ms) instead of dateparser, so it's the most accurate
of the four.

### Glints quirk

Glints' `posted_date` from `__NEXT_DATA__` is the listing **creation** date,
not when it was last refreshed/reposted. A job that's been re-shared today
may still show as months old to the filter. Expect Glints to dry up first
under tight `max_age_hours`. There is no public server-side recency param
on Glints' search URL.

### Indeed selectors

Indeed card-level selectors don't expose posted dates in the current
markup, so the parser reads `formattedRelativeTime` and `pubDate` from the
embedded `mosaic-data` JSON, paired by document order with each `jobkey`.
This is why Indeed's `posted_at` is reliable despite empty `posted_date`
on the visible card.

## Location coverage examples

Free-form values seen across keywords (sample from a 60-job audit):

| Site      | Examples seen                                               |
|-----------|-------------------------------------------------------------|
| jobstreet | Jakarta Barat, Jakarta Selatan, Jakarta Timur, Cikarang, Sidoarjo, Semarang, Bali |
| glints    | Jakarta Selatan, Buleleng, Setu, Pasar Minggu, Cilandak, Cengkareng, Batununggal |
| linkedin  | Jakarta, Indonesia, Area DKI Jakarta, Batam                 |
| indeed    | Jakarta, Bandung, Bekasi, Remote                            |

Use substring filters (`location: jakarta`) to catch variants like
"Jakarta Barat", "Area DKI Jakarta", "Jakarta Selatan", etc. in one shot.

## Per-site canonical value vocabulary

Values Glints normalizes into the canonical schema:

| Field             | Glints emits                                            |
|-------------------|---------------------------------------------------------|
| `employment_type` | `full-time`, `part-time`, `contract`, `internship`, `freelance` |
| `work_type`       | `onsite`, `remote`, `hybrid`                            |
| `experience_level`| `entry`, `junior`, `mid`, `senior`, `0+ years`, `1+ years`, … |

Other sites currently emit `null` for these fields — they pass the filter
via the null-rule.

## Anti-bot considerations

| Site      | Cloudscraper alone | Playwright fallback         |
|-----------|--------------------|------------------------------|
| jobstreet | works              | not needed                   |
| glints    | works              | not needed                   |
| linkedin  | works (guest API)  | not needed                   |
| indeed    | 403                | required (extra ~10-15s, ~280MB Chromium) |

Indeed's 403 is consistent and not a transient failure — every run hits
the playwright fallback. RAM cost matters when scaling `concurrency`.

## Adding new sites

The four current sites cover Indonesia-focused job boards. To add another
(jobsdb, kalibrr, etc.), see `adding-a-site.md` (TBD) — short version:

1. Add `scraper/sites/<name>.py` with a `Scraper` subclass implementing `parse(html)`.
2. Register the class in `scraper/sites/__init__.py::SCRAPERS`.
3. Add an entry under `sites:` in `config.yaml` with a `url_template`.
4. The runner picks it up automatically — no other changes needed.
