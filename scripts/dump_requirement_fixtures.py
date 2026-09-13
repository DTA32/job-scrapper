"""Dump scraped `requirements` outlines into the bot's extractor fixture corpus.

Run a scrape first (for example `python -m scraper -c <config>`), then:

    python scripts/dump_requirement_fixtures.py <output_dir> [--out cron/fixtures/requirements]

Every job with a non-empty outline becomes `<site>-<job id>.txt`. Contact details
are redacted so the corpus can be committed. Existing fixtures are overwritten;
fixtures for jobs absent from this scrape are left alone, so hand-labelled goldens
keep their inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "cron" / "fixtures" / "requirements"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_WHATSAPP = re.compile(r"wa\.me/\d+", re.IGNORECASE)
_ID_MOBILE = re.compile(r"(?<!\d)(?:\+62|62|0)8\d{1,2}[\s.-]?\d{3,4}[\s.-]?\d{3,5}(?!\d)")
_INTL_PHONE = re.compile(r"\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}")


def redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    text = _WHATSAPP.sub("wa.me/[phone]", text)
    text = _ID_MOBILE.sub("[phone]", text)
    return _INTL_PHONE.sub("[phone]", text)


def fixture_name(job: dict) -> str:
    ident = str(job.get("job_id") or "") or hashlib.sha1(str(job.get("url")).encode()).hexdigest()
    ident = re.sub(r"[^A-Za-z0-9_-]+", "-", ident)[:12].strip("-")
    return f"{job['site']}-{ident}.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "output_dir", type=Path, help="scraper output_dir holding <keyword>/<site>.json"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"fixture directory (default {DEFAULT_OUT})"
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for path in sorted(args.output_dir.glob("*/*.json")):
        if path.name.endswith(".raw.json"):
            continue
        payload = json.loads(path.read_text())
        for job in payload.get("jobs", []):
            outline = job.get("requirements")
            if not isinstance(outline, str) or not outline.strip():
                continue
            name = fixture_name(job)
            if name in written:
                continue  # the same posting under a second keyword
            written[name] = redact(outline).rstrip() + "\n"

    for name, text in written.items():
        (args.out / name).write_text(text)
    print(f"wrote {len(written)} fixture(s) to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
