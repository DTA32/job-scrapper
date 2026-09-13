"""Turn job-description markup into the outline text the bot extracts bullets from.

Descriptions arrive as HTML (search APIs, detail pages, embedded JSON) or as plain
text. Flattening them with get_text() throws away the only signal a rule-based
extractor has for finding the qualifications section -- which lines are headings and
which are list items -- so this keeps that structure in a small line dialect:

    ## <heading>    an <h1>-<h6>, or a line whose only content is bold text
    - <item>        an <li>, or a line opening with a bullet glyph, "1." or "1)"
    (blank line)    paragraph break

Every other non-empty line is plain text. Plain-text input goes through the same
line normalization, which makes the conversion idempotent on its own output.
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# Recorded on every run document whose `requirements` come from this module, so tools
# reading stored runs can tell outline text from the older flattened or 600-char
# window text (seeds/requirement_samples.runner.js harvests only these runs).
OUTLINE_FORMAT = "outline-v1"

# Control characters marking structure inside the parsed tree. Input is stripped of
# control characters first, so they cannot collide with real text.
_HEAD = "\x01"
_ITEM = "\x02"
_BOLD_OPEN = "\x03"
_BOLD_CLOSE = "\x04"
_BREAK = "\x05"
_BR = "\x06"

# Longest bold-only line still read as a heading; a longer one is emphasised prose.
_MAX_HEADING_CHARS = 80

_HTML_TAG = re.compile(
    r"<\s*/?\s*(?:p|br|li|ul|ol|div|span|strong|b|em|i|u|h[1-6]|section|article"
    r"|table|tr|td|th|blockquote|pre|hr)\b[^>]*>",
    re.IGNORECASE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿]")
_INLINE_SPACE = re.compile(r"[ \t  -   　]+")
_SOURCE_BREAK = re.compile(r"[\r\n  ]+")
_LINE_BREAK = re.compile(r"\r\n|[\r\n  ]")
_BULLET = re.compile(r"^(?:[-–—•·●○◦▪■□►▶➢➤*»]|\(?\d{1,2}[.)])\s+")
_BOLD_SPAN = re.compile(f"{_BOLD_OPEN}[^{_BOLD_CLOSE}]*{_BOLD_CLOSE}")
_MARKERS = re.compile(f"[{_HEAD}{_ITEM}{_BOLD_OPEN}{_BOLD_CLOSE}{_BREAK}{_BR}]")
# Rules and stray markdown markers, e.g. a "------" line or the lone "**" an editor left behind.
_DECORATION = re.compile(r"^[-=_*~•·—–\s]+$")
_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*")

_DROP_TAGS = ["script", "style", "noscript", "template", "head"]
_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
_BLOCK_TAGS = [
    "p", "div", "section", "article", "header", "footer", "blockquote", "pre",
    "table", "dl", "dt", "dd", "figure", "hr", "ul", "ol",
]  # fmt: skip

Line = tuple[str, str]  # (kind, text): kind is "heading" | "item" | "text" | "break"


def html_to_outline(value: object) -> str | None:
    """Convert a description (HTML or plain text) to outline text, or None if empty."""
    if not isinstance(value, str):
        return None
    cleaned = _CONTROL.sub("", value)
    if not cleaned.strip():
        return None
    lines = _markup_lines(cleaned) if _HTML_TAG.search(cleaned) else _text_lines(cleaned)
    return _assemble(lines)


def _markup_lines(markup: str) -> list[Line]:
    soup = BeautifulSoup(markup, "lxml")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    # Newlines in HTML source are plain whitespace; only markup decides line breaks.
    for node in soup.find_all(string=True):
        if node.find_parent("pre") is None:
            node.replace_with(_SOURCE_BREAK.sub(" ", str(node)))

    for tag in soup.find_all(["strong", "b"]):
        if tag.find_parent(["strong", "b"]) is None:
            _hoist_edge_breaks(tag)
            tag.insert(0, _BOLD_OPEN)
            tag.append(_BOLD_CLOSE)
    for tag in soup.find_all("li"):
        tag.insert_before(f"\n{_ITEM}")
        tag.insert_after("\n")
    for tag in soup.find_all(_HEADING_TAGS):
        tag.insert_before(f"\n{_BREAK}\n{_HEAD}")
        tag.insert_after(f"\n{_BREAK}\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        if tag.find_parent("li") is not None:
            # A <p> inside an <li> stays on the item's line; a nested list still
            # starts new items, because its own <li> markers break the line.
            tag.insert_before(" ")
            tag.insert_after(" ")
        else:
            tag.insert_before(f"\n{_BREAK}\n")
            tag.insert_after(f"\n{_BREAK}\n")
    for tag in soup.find_all(["td", "th"]):
        tag.insert_after(" ")
    for tag in soup.find_all("tr"):
        tag.insert_after("\n")
    for tag in soup.find_all("br"):
        tag.replace_with(f"{_BR}\n")

    lines: list[Line] = []
    for raw in soup.get_text().split("\n"):
        had_br = _BR in raw
        line = _normalize(raw.replace(_BR, ""))
        bare = _normalize(_MARKERS.sub("", line))
        if not bare:
            # A block edge, or a <br> that ends an empty line: <br><br> is a paragraph
            # break, a single <br> only a line break.
            if _BREAK in line or had_br:
                lines.append(("break", ""))
            continue
        if line.startswith(_HEAD) or (not line.startswith(_ITEM) and _is_bold_only(line)):
            heading = bare.rstrip(" :：")
            if heading:
                lines.append(("heading", heading))
        elif line.startswith(_ITEM):
            item = _BULLET.sub("", bare, count=1).strip()
            if item:
                lines.append(("item", item))
        else:
            classified = _classify(bare)
            if classified:
                lines.append(classified)
    return lines


def _text_lines(text: str) -> list[Line]:
    lines: list[Line] = []
    for raw in _LINE_BREAK.split(html.unescape(text)):
        bare = _normalize(raw)
        if not bare:
            lines.append(("break", ""))
            continue
        classified = _classify(bare)
        if classified:
            lines.append(classified)
    return lines


def _classify(line: str) -> Line | None:
    if line.startswith("## "):
        heading = line[3:].strip()
        return ("heading", heading) if heading else None
    if _DECORATION.match(line):
        return ("break", "")
    if line.startswith("**"):
        # Markdown typed into a rich-text editor: "**About Kulu**", or "**About Kulu"
        # with the closing marker stranded on a later line.
        inner = line.strip("*").strip().rstrip(" :：")
        if (
            inner
            and "**" not in inner
            and len(inner) <= _MAX_HEADING_CHARS
            and not inner.endswith((".", "!", "?"))
            and any(ch.isalpha() for ch in inner)
        ):
            return ("heading", inner)
    line = _MARKDOWN_BOLD.sub(r"\1", line)
    match = _BULLET.match(line)
    if match:
        item = line[match.end() :].strip()
        return ("item", item) if item else None
    return ("text", line)


def _hoist_edge_breaks(tag: Tag) -> None:
    """Move <br>s and blank text at the edges of a bold run outside it, so
    `<strong>About The Role<br><br></strong>` still reads as a bold-only line."""
    while tag.contents and _is_edge_filler(tag.contents[-1]):
        tag.insert_after(tag.contents[-1].extract())
    while tag.contents and _is_edge_filler(tag.contents[0]):
        tag.insert_before(tag.contents[0].extract())


def _is_edge_filler(node: object) -> bool:
    if isinstance(node, Tag):
        return node.name == "br"
    return isinstance(node, NavigableString) and not node.strip()


def _is_bold_only(line: str) -> bool:
    if not line.startswith(_BOLD_OPEN):
        return False
    if _BOLD_SPAN.sub("", line).strip(" :：-–—"):
        return False
    inner = _normalize(_MARKERS.sub("", line))
    return 0 < len(inner) <= _MAX_HEADING_CHARS and any(ch.isalpha() for ch in inner)


def _normalize(text: str) -> str:
    return _INLINE_SPACE.sub(" ", _ZERO_WIDTH.sub("", text)).strip()


def _assemble(lines: list[Line]) -> str | None:
    out: list[str] = []
    pending_break = False
    for kind, text in lines:
        if kind == "break":
            pending_break = True
            continue
        if out:
            after_heading = out[-1].startswith("## ")
            # Headings always open a new paragraph; content directly under a heading
            # never gets a blank line, so the heading stays attached to its body.
            if kind == "heading" or (pending_break and not after_heading):
                out.append("")
        pending_break = False
        if kind == "heading":
            out.append(f"## {text}")
        elif kind == "item":
            out.append(f"- {text}")
        else:
            out.append(text)
    return "\n".join(out) or None
