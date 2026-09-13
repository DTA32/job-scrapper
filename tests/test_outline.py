from __future__ import annotations

import pytest

from scraper.sites._text import html_to_outline


def test_list_items_follow_a_paragraph():
    html = "<p>Intro text</p><ul><li>Python</li><li>SQL</li></ul>"
    assert html_to_outline(html) == "Intro text\n\n- Python\n- SQL"


def test_heading_tag_stays_attached_to_its_list():
    assert html_to_outline("<h3>Requirements</h3><ul><li>Go</li></ul>") == "## Requirements\n- Go"


def test_bold_only_paragraph_is_a_heading_without_its_colon():
    html = "<p><strong>Kualifikasi:</strong></p><ul><li>S1 Informatika</li></ul>"
    assert html_to_outline(html) == "## Kualifikasi\n- S1 Informatika"


def test_bold_label_followed_by_text_is_not_a_heading():
    assert html_to_outline("<p><strong>Note:</strong> apply before Friday</p>") == (
        "Note: apply before Friday"
    )


def test_br_separated_glyph_lines_become_items():
    html = "<p><b>Requirements</b><br>• Python<br>• 2 years of SQL</p>"
    assert html_to_outline(html) == "## Requirements\n- Python\n- 2 years of SQL"


def test_breaks_inside_bold_do_not_hide_the_heading():
    # LinkedIn's markup wraps the line breaks inside the bold run.
    html = (
        "<strong>About The Role<br/><br/></strong>Traveloka builds.<br/><br/>"
        "<strong>Key Responsibilities<br/><br/></strong><ul><li>Ship</li></ul>"
    )
    assert html_to_outline(html) == (
        "## About The Role\nTraveloka builds.\n\n## Key Responsibilities\n- Ship"
    )


def test_double_br_is_a_paragraph_break_and_single_br_a_line_break():
    assert html_to_outline("<p>One<br>Two<br><br>Three</p>") == "One\nTwo\n\nThree"


def test_markdown_bold_typed_into_an_editor_is_a_heading():
    # JobStreet: "**About Kulu" with the closing "**" stranded in the next paragraph.
    html = "<p>Intro.</p><p>**About Kulu</p><p>**</p><p>Kulu is a **small** team.</p>"
    assert html_to_outline(html) == "Intro.\n\n## About Kulu\nKulu is a small team."


def test_decorative_rules_are_paragraph_breaks():
    assert html_to_outline("Requirements\n------------\n- Go") == "Requirements\n\n- Go"


def test_paragraph_inside_list_item_stays_on_the_item_line():
    html = "<ul><li><p>Python</p></li><li><p>SQL</p></li></ul>"
    assert html_to_outline(html) == "- Python\n- SQL"


def test_nested_list_items_are_flattened():
    assert html_to_outline("<ul><li>Skills<ul><li>Go</li></ul></li></ul>") == "- Skills\n- Go"


def test_entities_nbsp_and_zero_width_are_normalized():
    assert html_to_outline("<p>R&amp;D&nbsp;team​ builds APIs</p>") == "R&D team builds APIs"


def test_source_newlines_are_whitespace():
    assert html_to_outline("<p>Build\n    REST APIs</p>") == "Build REST APIs"


def test_script_and_style_are_dropped():
    assert html_to_outline("<style>.x{}</style><p>Hello</p><script>var a=1</script>") == "Hello"


def test_long_bold_paragraph_is_emphasis_not_a_heading():
    out = html_to_outline(f"<p><strong>{'word ' * 30}</strong></p>")
    assert out is not None
    assert not out.startswith("## ")


def test_plain_text_bullets_and_numbering_become_items():
    text = "Requirements:\n• Python\n1. SQL\n(2) Docker\n\n\nAbout us"
    assert html_to_outline(text) == "Requirements:\n- Python\n- SQL\n- Docker\n\nAbout us"


def test_conversion_is_idempotent():
    html = (
        "<p>Intro</p><h3>Requirements</h3><ul><li>Go</li></ul><p><b>Benefits</b></p><p>Laptop</p>"
    )
    once = html_to_outline(html)
    assert once == "Intro\n\n## Requirements\n- Go\n\n## Benefits\nLaptop"
    assert html_to_outline(once) == once


@pytest.mark.parametrize("value", [None, "", "   ", "<p> </p>", 42])
def test_empty_values_become_none(value):
    assert html_to_outline(value) is None
