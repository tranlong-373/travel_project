from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .normalizers import normalize_common_typos, normalize_key


CATALOG_PATH = Path(__file__).resolve().parent / "data" / "suggestion_catalog.json"

_FALLBACK_CATALOG: dict[str, Any] = {
    "locations": [
        {
            "key": "ho_chi_minh",
            "name": "Thành phố Hồ Chí Minh",
            "type": "city",
            "aliases": ["tp hcm", "tphcm", "sai gon", "sài gòn", "ho chi minh", "hcm"],
        },
        {
            "key": "ha_noi",
            "name": "Hà Nội",
            "type": "city",
            "aliases": ["ha noi", "hanoi", "hn"],
        },
        {
            "key": "thu_duc",
            "name": "Thủ Đức",
            "type": "district",
            "parent": "Thành phố Hồ Chí Minh",
            "aliases": ["thu duc", "tp thu duc", "thành phố thủ đức"],
        },
    ],
    "amenities": [
        {
            "key": "parking",
            "name": "Đỗ xe",
            "type": "amenity",
            "aliases": ["parking", "bãi đỗ xe", "chỗ đỗ xe", "chỗ đậu xe", "đậu xe", "có parking"],
        },
        {
            "key": "air_conditioner",
            "name": "Máy lạnh",
            "type": "amenity",
            "aliases": ["máy lạnh", "điều hòa", "air conditioner", "ac", "có máy lạnh"],
        },
        {
            "key": "pool",
            "name": "Hồ bơi",
            "type": "amenity",
            "aliases": ["hồ bơi", "bể bơi", "pool", "có hồ bơi"],
        },
    ],
    "poi_keywords": [
        {
            "key": "cafe",
            "name": "Quán cafe",
            "type": "poi",
            "aliases": ["cafe", "cà phê", "ca phe", "quán cafe", "quán cà phê"],
        },
        {
            "key": "atm",
            "name": "ATM",
            "type": "poi",
            "aliases": ["atm", "cây atm", "máy rút tiền"],
        },
        {
            "key": "cinema",
            "name": "Rạp chiếu phim",
            "type": "poi",
            "aliases": ["rạp phim", "rạp chiếu phim", "cinema", "cgv", "lotte cinema"],
        },
    ],
    "accommodation_types": [
        {
            "key": "hotel",
            "name": "Khách sạn",
            "type": "accommodation_type",
            "aliases": ["khach san", "khách sạn", "ks", "hotel"],
        },
        {
            "key": "homestay",
            "name": "Homestay",
            "type": "accommodation_type",
            "aliases": ["homestay", "home stay", "homstay", "homestate", "honestay"],
        },
        {
            "key": "hostel",
            "name": "Hostel",
            "type": "accommodation_type",
            "aliases": ["hostel", "nhà trọ", "nha tro", "trọ", "tro"],
        },
        {
            "key": "apartment",
            "name": "Căn hộ",
            "type": "accommodation_type",
            "aliases": ["căn hộ", "can ho", "chung cư", "chung cu", "apartment", "studio"],
        },
    ],
    "search_stopwords": [
        "tìm",
        "kiếm",
        "gợi",
        "ý",
        "cho",
        "ở",
        "gần",
        "quanh",
        "xung quanh",
        "cạnh",
        "kế",
        "sát",
        "near",
        "around",
        "mình",
        "tôi",
        "muốn",
        "cần",
        "thuê",
        "book",
        "khách",
        "sạn",
        "hotel",
        "homestay",
        "hostel",
        "căn",
        "hộ",
        "nhà",
        "chỗ",
    ],
}

_CATALOG_KEYS = ("locations", "amenities", "poi_keywords", "accommodation_types")
_NEAR_CUE_RE = re.compile(r"\b(?:gan|near|quanh|xung quanh|sat|canh|ke)\b")


@lru_cache(maxsize=1)
def load_suggestion_catalog() -> dict[str, Any]:
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        raw = _FALLBACK_CATALOG
    return _normalize_catalog(raw)


def clear_suggestion_catalog_cache() -> None:
    load_suggestion_catalog.cache_clear()


def normalize_text(text: Any) -> str:
    value = normalize_common_typos("" if text is None else str(text))
    value = normalize_key(value)
    value = re.sub(r"[^\w\s.]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().lower()


def compact_text(text: Any) -> str:
    return normalize_text(text).replace(" ", "")


def tokens(text: Any) -> set[str]:
    return {token for token in re.split(r"\s+", normalize_text(text)) if token}


def catalog_entries(section: str | None = None) -> list[dict[str, Any]]:
    catalog = load_suggestion_catalog()
    if section:
        return list(catalog.get(section) or [])
    entries: list[dict[str, Any]] = []
    for key in _CATALOG_KEYS:
        entries.extend(catalog.get(key) or [])
    return entries


def catalog_search_stopwords() -> set[str]:
    raw_words = load_suggestion_catalog().get("search_stopwords")
    if not isinstance(raw_words, list):
        raw_words = _FALLBACK_CATALOG["search_stopwords"]
    output: set[str] = set()
    for word in raw_words:
        normalized = normalize_text(word)
        if normalized:
            output.update(tokens(normalized))
    return output


def catalog_label(kind: str, key_or_label: Any) -> str:
    raw = "" if key_or_label is None else str(key_or_label)
    if not raw:
        return raw
    section = {
        "amenity": "amenities",
        "poi": "poi_keywords",
        "location": "locations",
        "accommodation_type": "accommodation_types",
    }.get(kind, kind)
    norm = normalize_text(raw)
    for entry in catalog_entries(section):
        values = [entry.get("key"), entry.get("name"), *(entry.get("aliases") or [])]
        if norm in {normalize_text(value) for value in values if value}:
            return str(entry.get("name") or raw)
    return raw


def detect_nearby_poi(text: Any) -> dict[str, Any] | None:
    query = normalize_text(text)
    if not query or not _NEAR_CUE_RE.search(query):
        return None

    query_tokens = tokens(query)
    best: tuple[int, dict[str, Any], str, set[str]] | None = None
    for entry in catalog_entries("poi_keywords"):
        for alias in _entry_aliases(entry):
            alias_norm = normalize_text(alias)
            if not alias_norm or alias_norm not in query:
                continue
            alias_tokens = tokens(alias_norm)
            meaningful = query_tokens - alias_tokens - catalog_search_stopwords()
            score = len(alias_tokens)
            if meaningful:
                continue
            if best is None or score > best[0]:
                best = (score, entry, alias, alias_tokens)

    if best is None:
        return None
    _, entry, alias, _alias_tokens = best
    return {
        "key": str(entry.get("key") or normalize_text(entry.get("name")).replace(" ", "_")),
        "name": str(entry.get("name") or alias),
        "type": "poi",
        "matched_alias": alias,
        "subtitle": str(entry.get("subtitle") or "Loại địa điểm"),
    }


def _normalize_catalog(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else _FALLBACK_CATALOG
    catalog: dict[str, list[dict[str, Any]]] = {}
    for section in _CATALOG_KEYS:
        values = source.get(section)
        if not isinstance(values, list):
            values = _FALLBACK_CATALOG.get(section, [])
        catalog[section] = [_normalize_entry(item) for item in values if isinstance(item, dict)]
    stopwords = source.get("search_stopwords")
    catalog["search_stopwords"] = stopwords if isinstance(stopwords, list) else list(_FALLBACK_CATALOG["search_stopwords"])
    return catalog


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    name = str(entry.get("name") or "").strip()
    key = str(entry.get("key") or normalize_text(name).replace(" ", "_")).strip()
    aliases = _unique_aliases([name, key, *(entry.get("aliases") or [])])
    normalized = dict(entry)
    normalized["key"] = key
    normalized["name"] = name or key
    normalized["aliases"] = aliases
    normalized["normalized_aliases"] = [normalize_text(alias) for alias in aliases]
    return normalized


def _entry_aliases(entry: dict[str, Any]) -> list[str]:
    return _unique_aliases([entry.get("name"), entry.get("key"), *(entry.get("aliases") or [])])


def _unique_aliases(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        norm = normalize_text(text)
        if not text or not norm or norm in seen:
            continue
        seen.add(norm)
        output.append(text)
    return output
