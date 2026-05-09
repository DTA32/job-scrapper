from __future__ import annotations

import json
from typing import Any, Callable

from bs4 import BeautifulSoup


def extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def walk_dicts(
    obj: Any, predicate: Callable[[dict], bool], out: list[dict]
) -> None:
    if isinstance(obj, dict):
        if predicate(obj):
            out.append(obj)
        for value in obj.values():
            walk_dicts(value, predicate, out)
    elif isinstance(obj, list):
        for item in obj:
            walk_dicts(item, predicate, out)
