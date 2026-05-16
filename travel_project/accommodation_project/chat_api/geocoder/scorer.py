from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from ..normalizers import normalize_key
from .validator import BLOCKED_POI_CATEGORIES, GeocodeValidation, geocode_category

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
    "dia",
    "di",
    "du",
    "lich",
    "pho",
    "phuong",
    "duong",
    "street",
    "road",
    "place",
    "landmark",
    "ho",
    "chi",
    "minh",
    "hcm",
    "tphcm",
    "tp",
    "city",
    "viet",
    "nam",
    "vietnam",
}

GOOD_PLACE_CATEGORIES = {
    "aeroway",
    "aerodrome",
    "airport",
    "attraction",
    "historic",
    "landmark",
    "monument",
    "museum",
    "pedestrian",
    "tourism",
    "university",
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
    if not validation.inside_hcm:
        return CandidateScore(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    phrase_key = normalize_key(phrase or "")
    display = normalize_key(str(item.get("display_name") or item.get("name") or item.get("canonical_name") or ""))
    name = normalize_key(str(item.get("name") or item.get("canonical_name") or "").split(",")[0])
    display_head = normalize_key(str(item.get("display_name") or "").split(",")[0])
    name_similarity = max(_ratio(phrase_key, display_head), _ratio(phrase_key, name), _ratio(phrase_key, display))

    haystack_parts = [display, name]
    address = item.get("address") or {}
    if isinstance(address, dict):
        haystack_parts.extend(normalize_key(str(value)) for value in address.values() if value)
    haystack = " ".join(haystack_parts)

    tokens = _meaningful_tokens(phrase_key)
    token_coverage = 0.0 if not tokens else sum(1 for token in tokens if token in haystack) / len(tokens)
    category_score = _category_score(geocode_category(item))
    city_score = 1.0 if validation.address_matches_hcm else 0.85
    importance_score = _importance_score(item.get("importance"))

    total = (
        name_similarity * 0.32
        + token_coverage * 0.34
        + category_score * 0.14
        + city_score * 0.12
        + importance_score * 0.08
    )
    return CandidateScore(min(total, 0.99), name_similarity, token_coverage, category_score, city_score, importance_score)


def _meaningful_tokens(text: str | None) -> list[str]:
    norm = normalize_key(text or "")
    tokens = re.findall(r"\w+", norm)
    return [token for token in tokens if (token.isdigit() or len(token) > 2) and token not in PLACE_STOPWORDS]


def _category_score(category: str) -> float:
    key = normalize_key(category)
    if key in BLOCKED_POI_CATEGORIES:
        return 0.0
    if any(token in key for token in GOOD_PLACE_CATEGORIES):
        return 1.0
    if key in {"administrative", "suburb", "city", "district", "road", "highway", "amenity"}:
        return 0.75
    return 0.55


def _importance_score(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if fuzz is not None:
        return fuzz.partial_ratio(left, right) / 100
    if left in right or right in left:
        return 0.95
    return difflib.SequenceMatcher(None, left, right).ratio()

