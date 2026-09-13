from __future__ import annotations

import json

from scraper.sites.glints import GlintsScraper
from scraper.sites.jobstreet import JobstreetScraper
from scraper.sites.linkedin import LinkedinScraper

_DESCRIPTION = "<p><strong>Requirements:</strong></p><ul><li>Go</li><li>SQL</li></ul>"
_OUTLINE = "## Requirements\n- Go\n- SQL"


def test_jobstreet_next_data_html_is_outlined():
    payload = {"props": {"pageProps": {"job": {"jobDescription": _DESCRIPTION}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    scraper = JobstreetScraper(url="https://id.jobstreet.com/id/go-jobs", limit=1)
    assert scraper.parse_detail(html) == _OUTLINE


def test_jobstreet_detail_selector_is_outlined():
    html = f'<div data-automation="jobAdDetails">{_DESCRIPTION}</div>'
    scraper = JobstreetScraper(url="https://id.jobstreet.com/id/go-jobs", limit=1)
    assert scraper.parse_detail(html) == _OUTLINE


def test_glints_jsonld_description_is_outlined():
    payload = {"@type": "JobPosting", "description": _DESCRIPTION}
    html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'
    scraper = GlintsScraper(
        url="https://glints.com/id/opportunities/jobs/explore?keyword=go", limit=1
    )
    assert scraper.parse_detail(html) == _OUTLINE


def test_linkedin_description_is_outlined():
    html = f'<div class="show-more-less-html__markup">{_DESCRIPTION}</div>'
    scraper = LinkedinScraper(url="https://www.linkedin.com/jobs-guest/x?keywords=go", limit=1)
    assert scraper.parse_detail(html) == _OUTLINE
