from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

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


# normalized colloquial form -> kode. Escape hatch for names absent from the
# official dataset (verified missing: "Jakarta Raya").
ALIASES: dict[str, str] = {
    "jakarta raya": "31",
    "dki jakarta": "31",
    "dki": "31",
}


@dataclass(frozen=True)
class WilayahIndex:
    by_name: dict[str, list[str]]  # normalized nama (full AND stripped) -> [kode,...]
    entries: tuple[tuple[str, str], ...]  # (kode, normalized_full_nama) for dot-count <= 1


def _add(by_name: dict[str, list[str]], key: str, kode: str) -> None:
    bucket = by_name.setdefault(key, [])
    if kode not in bucket:
        bucket.append(kode)


def build_index_from_rows(rows: Iterable[tuple[str, str]]) -> WilayahIndex:
    by_name: dict[str, list[str]] = {}
    entries: list[tuple[str, str]] = []
    for kode, nama in rows:
        if kode.count(".") > 2:  # exclude villages (also kills name collisions)
            continue
        norm_full = normalize(nama)
        if not norm_full:
            continue
        _add(by_name, norm_full, kode)
        stripped = strip_qualifiers(norm_full)
        if stripped and stripped != norm_full:
            _add(by_name, stripped, kode)
        if kode.count(".") <= 1:  # province + city only, for term_to_prefixes
            entries.append((kode, norm_full))
    return WilayahIndex(by_name=by_name, entries=tuple(entries))


def candidate_kodes(
    location: str, index: WilayahIndex, aliases: dict[str, str] = ALIASES
) -> set[str]:
    norm = normalize(location)
    if not norm:
        return set()
    forms = segments(norm)
    if norm not in forms:
        forms = [*forms, norm]
    out: set[str] = set()
    for form in forms:
        for candidate in (form, strip_qualifiers(form)):
            if not candidate:
                continue
            if candidate in aliases:
                out.add(aliases[candidate])
            out.update(index.by_name.get(candidate, ()))
    return out


def location_in_scope(
    location: str, index: WilayahIndex, prefixes: set[str] | frozenset[str]
) -> bool:
    if not prefixes:
        return False
    return any(is_under(k, prefixes) for k in candidate_kodes(location, index))


def _has_token(haystack: str, token: str) -> bool:
    return re.search(r"\b" + re.escape(token) + r"\b", haystack) is not None


def term_to_prefixes(term: str, entries: tuple[tuple[str, str], ...]) -> set[str] | None:
    t = normalize(term)
    matched = [kode for kode, nname in entries if _has_token(nname, t)]
    if not matched:
        return None  # no province/city => literal term
    tops = {k for k in matched if not any(o != k and is_under(k, {o}) for o in matched)}
    return tops
