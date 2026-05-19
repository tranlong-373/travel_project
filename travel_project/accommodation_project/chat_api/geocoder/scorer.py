from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..normalizers import normalize_key
from .validator import (
    BLOCKED_POI_CATEGORIES,
    GeocodeValidation,
    candidate_text_for_matching,
    geocode_category,
    is_named_map_anchor_proxy,
    normalize_anchor_text,
    name_similarity as validated_name_similarity,
    normalize_vi,
    token_coverage as validated_token_coverage,
)

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - rapidfuzz is optional.
    fuzz = None


PLACE_STOPWORDS = {
    "gan",
    "quanh",
    "xung",
    "canh",
    "ke",
    "sat",
    "near",
    "around",
    "close",
    "to",
    "khu",
    "vuc",
    "dia",
    "diem",
    "phuong",
    "duong",
    "street",
    "road",
    "ho",
    "chi",
    "minh",
    "hcm",
    "tphcm",
    "tp",
    "thanh",
    "city",
    "viet",
    "nam",
    "vietnam",
}

GOOD_PLACE_CATEGORIES = {
    "aeroway",
    "aerodrome",
    "airport",
    "amenity",
    "attraction",
    "bank",
    "cafe",
    "college",
    "fast_food",
    "ferry_terminal",
    "guest_house",
    "historic",
    "hospital",
    "hostel",
    "hotel",
    "landmark",
    "leisure",
    "library",
    "mall",
    "market",
    "marketplace",
    "monument",
    "museum",
    "park",
    "pedestrian",
    "place_of_worship",
    "post_office",
    "railway",
    "restaurant",
    "school",
    "shopping_mall",
    "station",
    "temple",
    "theatre",
    "tourism",
    "university",
    "zoo",
}


@dataclass(frozen=True)
class CandidateScore:
    total: float
    name_similarity: float
    token_coverage: float
    category_score: float
    city_score: float
    importance_score: float

    def to_dict(self) -> dict[str, float]:
        return {
            "total": round(self.total, 3),
            "name_similarity": round(self.name_similarity, 3),
            "token_coverage": round(self.token_coverage, 3),
            "category_score": round(self.category_score, 3),
            "city_score": round(self.city_score, 3),
            "importance_score": round(self.importance_score, 3),
        }


def score_geocode_candidate(
    phrase: str,
    item: dict[str, Any],
    *,
    validation: GeocodeValidation,
) -> CandidateScore:
    if not (validation.inside_hcm or validation.address_matches_hcm):
        return CandidateScore(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    display = normalize_vi(str(item.get("display_name") or item.get("name") or item.get("canonical_name") or ""))
    name = normalize_vi(str(item.get("name") or item.get("canonical_name") or "").split(",")[0])
    display_head = normalize_vi(str(item.get("display_name") or "").split(",")[0])
    candidate_text = candidate_text_for_matching(item)
    base_similarity = validated_name_similarity(phrase, candidate_text)
    ordered_similarity = max(_ordered_token_score(phrase, name), _ordered_token_score(phrase, display_head))
    name_similarity = (
        max((base_similarity * 0.65) + (ordered_similarity * 0.35), ordered_similarity * 0.9)
        if ordered_similarity
        else base_similarity
    )
    map_anchor_proxy = is_named_map_anchor_proxy(item, phrase)
    if map_anchor_proxy:
        name_similarity = max(name_similarity, 0.86)

    haystack_parts = [display, name, candidate_text]
    address = item.get("address") or {}
    if isinstance(address, dict):
        haystack_parts.extend(normalize_vi(str(value)) for value in address.values() if value)
    haystack = " ".join(haystack_parts)

    category = geocode_category(item)
    category_score = _category_score(category)
    if map_anchor_proxy:
        category_score = max(category_score, 0.75)
    token_coverage = max(validation.token_coverage, validated_token_coverage(phrase, haystack))
    if validation.accepted and _trusted_poi_match(validation, category, name_similarity, category_score):
        token_coverage = max(token_coverage, 0.75 if name_similarity >= 0.9 else 0.65)
    city_score = _hcm_context_score(item) if validation.address_matches_hcm else 0.85
    importance_score = max(_importance_score(item.get("importance")), _place_rank_score(item.get("place_rank")))

    total = (
        name_similarity * 0.32
        + token_coverage * 0.34
        + category_score * 0.14
        + city_score * 0.12
        + importance_score * 0.08
    )
    if validation.accepted and _trusted_poi_match(validation, category, name_similarity, category_score):
        total += 0.08 if name_similarity >= 0.9 else 0.04
    return CandidateScore(min(total, 0.99), name_similarity, token_coverage, category_score, city_score, importance_score)


@lru_cache(maxsize=4096)
def _meaningful_tokens(text: str | None) -> tuple[str, ...]:
    norm = normalize_anchor_text(text)
    tokens = re.findall(r"\w+", norm)
    return tuple(token for token in tokens if (token.isdigit() or len(token) > 2) and token not in PLACE_STOPWORDS)


def _category_score(category: str) -> float:
    key = normalize_key(category)
    if any(token in key for token in GOOD_PLACE_CATEGORIES):
        return 1.0
    if key in BLOCKED_POI_CATEGORIES:
        return 0.0
    if key in {"administrative", "suburb", "city", "district", "road", "highway", "amenity"}:
        return 0.75
    return 0.55


def _importance_score(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _place_rank_score(value: Any) -> float:
    try:
        rank = float(value)
    except (TypeError, ValueError):
        return 0.0
    if rank <= 0:
        return 0.0
    return min(max((30.0 - rank) / 30.0, 0.0), 1.0)


def _trusted_poi_match(
    validation: GeocodeValidation,
    category: str,
    name_similarity: float,
    category_score: float,
) -> bool:
    if not (validation.inside_hcm or validation.address_matches_hcm):
        return False
    if name_similarity < 0.85:
        return False
    if category_score < 0.9:
        return False
    category_key = normalize_key(category)
    return any(token in category_key for token in GOOD_PLACE_CATEGORIES)


def _hcm_context_score(item: dict[str, Any]) -> float:
    lat = _float_or_none(item.get("lat") if item.get("lat") is not None else item.get("latitude"))
    lon = _float_or_none(item.get("lon") if item.get("lon") is not None else item.get("longitude"))
    if lat is None or lon is None:
        return 0.85
    center_lat, center_lon = 10.7758, 106.7004
    lat_km = (lat - center_lat) * 111.0
    lon_km = (lon - center_lon) * 111.0 * math.cos(math.radians(center_lat))
    distance_km = math.sqrt((lat_km * lat_km) + (lon_km * lon_km))
    return max(0.2, 1.0 - (distance_km / 55.0))


def _ordered_token_score(phrase: str, candidate_text: str) -> float:
    query_tokens = _meaningful_tokens(phrase)
    if len(query_tokens) < 2:
        return 0.0
    candidate = " ".join(_meaningful_tokens(candidate_text))
    if not candidate:
        return 0.0
    query = " ".join(query_tokens)
    if query in candidate:
        return 1.0
    best = 0.0
    for size in range(len(query_tokens) - 1, 1, -1):
        for index in range(0, len(query_tokens) - size + 1):
            chunk = " ".join(query_tokens[index : index + size])
            if chunk in candidate:
                best = max(best, size / len(query_tokens))
        if best:
            return best
    return 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if fuzz is not None:
        return fuzz.partial_ratio(left, right) / 100
    if left in right or right in left:
        return 0.95
    return difflib.SequenceMatcher(None, left, right).ratio()
