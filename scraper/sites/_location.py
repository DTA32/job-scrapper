from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_SEP = re.compile(r"\s*[,/·|]\s*|\s+-\s+")

# Multi-word leading qualifiers MUST be tried before single-word ones.
_LEADING_MULTI = (
    "daerah khusus ibukota",
    "daerah istimewa",
    "kota administrasi",
    "kabupaten administrasi",
)
_LEADING = (
    "kecamatan",
    "kabupaten",
    "kotamadya",
    "kelurahan",
    "provinsi",
    "administrasi",
    "kab",
    "kec",
    "kel",
    "prov",
    "kota",
    "desa",
    "area",
    "dki",
)
_TRAILING = ("dan sekitarnya", "dan sekitar")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower().strip()
    return _WS.sub(" ", s)


def strip_qualifiers(normalized: str) -> str:
    s = normalized
    for t in _TRAILING:
        if s == t:
            return normalized
        if s.endswith(" " + t):
            s = s[: -len(t)].strip()
    changed = True
    while changed:
        changed = False
        for q in (*_LEADING_MULTI, *_LEADING):
            prefix = q + " "
            if s.startswith(prefix):
                residue = s[len(prefix) :].strip()
                if residue:  # guard: never strip to empty
                    s = residue
                    changed = True
                    break
    return s


def segments(normalized: str) -> list[str]:
    parts = _SEP.split(normalized)
    return [p.strip(" -") for p in parts if p.strip(" -")]


def is_under(kode: str, prefixes: set[str] | frozenset[str]) -> bool:
    return any(kode == p or kode.startswith(p + ".") for p in prefixes)
