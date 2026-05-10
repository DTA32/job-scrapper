# Configuration reference

The runtime is driven entirely by `config.yaml` at the repo root. The loader
(`scraper/config_loader.py::load`) parses, validates, and resolves the file
into an `AppConfig` dataclass. Any malformed value raises `ConfigError` and
the run aborts — partial writes never reach disk.

This page documents every key the loader recognizes. For filter semantics
specifically, see [`filters.md`](filters.md).

## Top-level keys

```yaml
keywords: [software engineer, data analyst]   # required
limit: 2                                       # optional, default 2
concurrency: 2                                 # optional, default 2
output_dir: output                             # optional, default 'output'
max_age_hours: 24                              # optional, no default = no filter
default_fields: [...]                          # optional, default 4 fields
filter: {...}                                  # optional, no default = no filter
sites: {...}                                   # required, non-empty
```

### `keywords` (required)

List of strings. Each keyword is run against every enabled site, producing
a `(keyword, site)` cross-product. Output lands under
`output/<keyword-slug>/<site>.json`.

- Backwards-compatible alias: `keyword: <string>` is accepted and treated as
  a single-element list.
- Empty strings are rejected. Duplicates are silently de-duped.
- Each keyword is templated into the URL via `{keyword}`, `{keyword_slug}`,
  or `{keyword_plus}` (see "Site URL templating" below).

```yaml
# Multi-keyword
keywords:
  - software engineer
  - data analyst

# Single keyword (legacy form)
keyword: backend developer
```

### `limit` (optional, default `2`)

Integer, must be `>= 1`. Maximum number of jobs each site emits per
`(keyword, site)` pair.

```yaml
limit: 5
```

### `concurrency` (optional, default `2`)

Integer, must be `>= 1`. Maximum number of `(keyword, site)` pairs running
in parallel through a thread pool.

- `concurrency: 1` falls back to a sequential loop (no thread overhead).
- Each Playwright fallback consumes ~250-300MB RAM. Tune for available memory.

```yaml
concurrency: 4
```

### `output_dir` (optional, default `output`)

String path. Where per-site JSON files land. Resolved relative to the
working directory if not absolute.

```yaml
output_dir: ./scraper-output
```

### `max_age_hours` (optional, no default)

Integer, must be `>= 1` if set. Drops jobs whose parsed `posted_at` is
older than this many hours from now (UTC). Jobs with unparseable
`posted_date` are kept (conservative).

- Per-site override: `sites.<name>.max_age_hours` replaces the global.
- Pair this with the URL templates' server-side recency params for best results
  (e.g. jobstreet `?daterange=1`, linkedin `&f_TPR=r86400`, indeed `&fromage=1`).
  See `sites.md` for the full per-site param table.

```yaml
max_age_hours: 24
```

### `default_fields` (optional)

List of canonical field names to emit per Job. Default:
`[title, company, location, url]`.

Allowed canonical fields:

```
site                matched_keyword     title             company
url                 location            salary            posted_date
posted_at           work_type           employment_type   experience_level
job_id              requirements
```

- `site`, `matched_keyword`, `title`, `company`, `url` are **always
  included** regardless of this list (anchors).
- Unknown field names log a warning and are silently dropped — they don't
  abort the load.
- Per-site override: `sites.<name>.fields` replaces the global list.

```yaml
default_fields:
  - title
  - company
  - location
  - url
  - salary
  - posted_date
  - posted_at
```

### `filter` (optional)

Content filter applied after recency, before field projection. Each value
can be a single string or a list. Substring + case-insensitive.

See [`filters.md`](filters.md) for full reference.

```yaml
filter:
  location: [jakarta, bandung]
  employment_type: [full-time, internship]
  work_type: [remote, hybrid]
```

### `sites` (required)

Mapping from site-name → site config. Site name must match a registered
scraper in `scraper/sites/__init__.py::SCRAPERS`. Currently supported:

- `jobstreet`
- `glints`
- `linkedin`
- `indeed`

Each site entry:

```yaml
sites:
  <name>:
    enabled: true                                  # optional, default true
    url_template: "https://...?{keyword}..."       # required
    fields: [...]                                  # optional, overrides default_fields
    max_age_hours: 12                              # optional, overrides global
    filter: {...}                                  # optional, replaces global
    limit: 10                                      # optional, overrides global limit
```

#### `sites.<name>.enabled`

Boolean. Disabled sites are skipped during default runs. CLI args
(`python -m scraper jobstreet`) override and run regardless of this flag.

#### `sites.<name>.url_template`

String. The URL fetched per `(keyword, site)` pair. Three placeholders are
substituted:

| Placeholder       | Format                          | Example for `software engineer` |
|-------------------|---------------------------------|---------------------------------|
| `{keyword}`       | URL-encoded space (`%20`)       | `software%20engineer`           |
| `{keyword_slug}`  | lowercase + hyphens             | `software-engineer`             |
| `{keyword_plus}`  | plus-separated                  | `software+engineer`             |

Pick the one that matches the site's URL convention. The loader validates
all placeholders against this allowlist; unknown placeholder → `ConfigError`.

```yaml
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1"
  indeed:
    url_template: "https://id.indeed.com/jobs?q={keyword_plus}&l=Indonesia&fromage=1"
```

#### `sites.<name>.fields`

Optional list of canonical field names. Replaces (does not merge into)
`default_fields` for this site only. Same validation as `default_fields`.

#### `sites.<name>.max_age_hours`

Optional integer. Replaces the global `max_age_hours` for this site only.

#### `sites.<name>.filter`

Optional dict. Replaces (does not merge into) the global `filter` block for
this site only. Same shape as the global filter — see [`filters.md`](filters.md).

#### `sites.<name>.limit`

Optional positive integer. Replaces the global `limit` for this site only —
useful when one source's relevance ranking buries good matches deep in the
list (e.g. raise `sites.indeed.limit` so Jakarta jobs surface past the top
two non-Jakarta hits, while keeping other sites at the cheaper global limit).

## Validation rules summary

The loader (`load(path)`) enforces:

| Key                       | Rule                                             | On failure        |
|---------------------------|--------------------------------------------------|-------------------|
| `keywords` / `keyword`    | At least one non-empty string                    | `ConfigError`     |
| `limit`                   | Integer >= 1                                     | `ConfigError`     |
| `concurrency`             | Integer >= 1                                     | `ConfigError`     |
| `max_age_hours`           | Integer >= 1 or null                             | `ConfigError`     |
| `sites`                   | Non-empty mapping                                | `ConfigError`     |
| `sites.<name>.url_template` | Non-empty string with valid placeholders only  | `ConfigError`     |
| `default_fields` entries  | Strings; unknown names → warning, dropped       | `[config] warning` (load continues) |
| `filter` keys             | One of `location`, `employment_type`, `work_type`; unknown → warning, dropped | `[config] warning` |
| `filter` values           | String or list-of-strings                        | `ConfigError`     |

## Loading the resolved config

```python
from pathlib import Path
from scraper.config_loader import load

config = load(Path("config.yaml"))

config.keywords           # tuple[str, ...]
config.limit              # int
config.concurrency        # int
config.output_dir         # Path
config.default_fields     # tuple[str, ...]
config.max_age_hours      # int | None
config.filter             # dict[str, list[str]]
config.sites              # tuple[SiteConfig, ...]

config.fields_for("glints")    # frozenset[str]
config.max_age_for("glints")   # int | None
config.filter_for("glints")    # dict[str, list[str]]
```

## Live editing via MCP

The MCP server exposes `update_config` for safe runtime patching. See
[`mcp.md`](mcp.md) for the tool catalog and patch shape.

The patch path is preferred over direct file edits because the merged
result is validated through this same loader before being written to disk;
invalid patches return an error and leave the live file untouched.
