from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..normalizers import normalize_key
from .providers.nominatim import HCM_VIEWBOX

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - rapidfuzz is optional.
    fuzz = None


HCM_ADDRESS_TOKENS = (
    "ho chi minh",
    "thanh pho ho chi minh",
    "tp ho chi minh",
    "tp hcm",
    "tphcm",
    "hcm",
    "sai gon",
    "saigon",
)

BLOCKED_POI_CATEGORIES = {
    "cafe",
    "restaurant",
    "bar",
    "fast_food",
    "shop",
    "store",
    "spa",
    "salon",
    "hotel",
    "hostel",
    "guest_house",
    "apartment",
    "bus_stop",
}

MAP_ANCHOR_PROXY_CATEGORIES = {
    "bus_stop",
    "station",
    "tram_stop",
    "subway_entrance",
    "ferry_terminal",
    "public_transport",
    "platform",
}

FOOD_INTENT_TOKENS = {"an", "uong", "cafe", "ca phe", "restaurant", "quan an", "food"}
LODGING_INTENT_TOKENS = {"khach san", "hotel", "can ho", "apartment", "homestay", "hostel", "nha nghi"}
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
    "tich",
    "cong",
    "vien",
    "bao",
    "tang",
    "lang",
    "tp",
    "thanh",
    "pho",
    "ho",
    "chi",
    "minh",
    "hcm",
    "tphcm",
    "viet",
    "nam",
    "vietnam",
}


@dataclass(frozen=True)
class GeocodeValidation:
    accepted: bool
    reason: str
    inside_hcm: bool
    address_matches_hcm: bool
    category: str
    lat: float | None
    lon: float | None
    token_coverage: float = 0.0
    name_similarity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "inside_hcm": self.inside_hcm,
            "address_matches_hcm": self.address_matches_hcm,
            "category": self.category,
            "lat": self.lat,
            "lon": self.lon,
            "token_coverage": round(self.token_coverage, 3),
            "name_similarity": round(self.name_similarity, 3),
        }


def validate_geocode_candidate(
    item: dict[str, Any] | None,
    *,
    query: str | None = None,
    intent: str = "landmark",
    top_score: float | None = None,
    runner_up_score: float | None = None,
    explicit_venue: bool = False,
) -> GeocodeValidation:
    item = item or {}
    lat = _float_or_none(item.get("lat") if item.get("lat") is not None else item.get("latitude"))
    lon = _float_or_none(item.get("lon") if item.get("lon") is not None else item.get("longitude"))
    category = geocode_category(item)
    inside_hcm = is_inside_hcm(lat, lon)
    address_matches = address_mentions_hcm(item)
    coverage = token_coverage(query, _candidate_text(item)) if query else 0.0
    similarity = name_similarity(query, _candidate_text(item)) if query else 0.0

    if lat is None or lon is None:
        return GeocodeValidation(False, "missing_coordinates", False, address_matches, category, lat, lon, coverage, similarity)
    if not (inside_hcm or address_matches):
        return GeocodeValidation(False, "outside_hcm", inside_hcm, address_matches, category, lat, lon, coverage, similarity)
    if query and coverage < 0.65 and similarity < 0.82:
        return GeocodeValidation(False, "low_name_match", inside_hcm, address_matches, category, lat, lon, coverage, similarity)
    if query and not _candidate_matches_known_alias(query, item):
        return GeocodeValidation(False, "known_alias_mismatch", inside_hcm, address_matches, category, lat, lon, coverage, similarity)
    if is_blocked_category(item, intent=intent, query=query, explicit_venue=explicit_venue):
        return GeocodeValidation(False, f"blocked_category:{category}", inside_hcm, address_matches, category, lat, lon, coverage, similarity)
    if runner_up_score is not None and is_ambiguous(top_score, runner_up_score):
        return GeocodeValidation(False, "top1_top2_margin_too_small", inside_hcm, address_matches, category, lat, lon, coverage, similarity)
    return GeocodeValidation(True, "ok", inside_hcm, address_matches, category, lat, lon, coverage, similarity)


def normalize_vi(text: str | None) -> str:
    value = normalize_key(text or "")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def token_coverage(query: str | None, candidate_name: str | None) -> float:
    tokens = _meaningful_tokens(query)
    if not tokens:
        return 0.0
    haystack = normalize_vi(candidate_name)
    return sum(1 for token in tokens if token in haystack) / len(tokens)


def name_similarity(query: str | None, candidate_name: str | None) -> float:
    left = normalize_vi(query)
    right = normalize_vi(candidate_name)
    if not left or not right:
        return 0.0
    if fuzz is not None:
        return fuzz.partial_ratio(left, right) / 100
    if left in right or right in left:
        return 0.95
    import difflib

    return difflib.SequenceMatcher(None, left, right).ratio()


def is_inside_hcm(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return (
        HCM_VIEWBOX.min_lat <= float(lat) <= HCM_VIEWBOX.max_lat
        and HCM_VIEWBOX.min_lon <= float(lon) <= HCM_VIEWBOX.max_lon
    )


def address_mentions_hcm(item: dict[str, Any] | str | None) -> bool:
    if isinstance(item, str):
        haystack_parts = [item]
    else:
        item = item or {}
        haystack_parts = [item.get("display_name") or "", item.get("name") or "", item.get("canonical_name") or ""]
        address = item.get("address") or {}
        if not address and not any(haystack_parts):
            address = item
        if isinstance(address, dict):
            haystack_parts.extend(str(value) for value in address.values() if value)
    haystack = normalize_key(" ".join(haystack_parts))
    return any(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", haystack) for token in HCM_ADDRESS_TOKENS)


def is_blocked_category(
    candidate: dict[str, Any] | None,
    *,
    intent: str = "landmark",
    query: str | None = None,
    explicit_venue: bool = False,
) -> bool:
    if explicit_venue:
        return False
    category = geocode_category(candidate or {})
    if category not in BLOCKED_POI_CATEGORIES:
        return False
    query_key = normalize_vi(query)
    if _has_intent_token(query_key, FOOD_INTENT_TOKENS):
        return False
    if _has_intent_token(query_key, LODGING_INTENT_TOKENS):
        return False
    if is_named_map_anchor_proxy(candidate, query):
        return False
    return intent in {"landmark", "poi", "near_anchor"}


def is_named_map_anchor_proxy(candidate: dict[str, Any] | None, query: str | None) -> bool:
    candidate = candidate or {}
    if geocode_category(candidate) not in MAP_ANCHOR_PROXY_CATEGORIES:
        return False
    query_tokens = _distinctive_tokens(query)
    if not query_tokens:
        return False
    if token_coverage(query, _candidate_text(candidate)) < 0.95:
        return False
    candidate_head = _candidate_head_text(candidate)
    return any(token in candidate_head for token in query_tokens)


def _has_intent_token(query_key: str, tokens: set[str]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", query_key) for token in tokens)


def is_ambiguous(top1: Any, top2: Any) -> bool:
    first = _score_value(top1)
    second = _score_value(top2)
    if first is None or second is None:
        return False
    return first - second < 0.08


def geocode_category(item: dict[str, Any]) -> str:
    for key in ("type", "kind", "place_type", "category", "class"):
        value = normalize_key(str(item.get(key) or ""))
        if value:
            return value
    return "unknown"


def rejected_geocoder_payload(
    item: dict[str, Any] | None,
    *,
    reason: str,
    validation: GeocodeValidation | None = None,
    score: float | None = None,
) -> dict[str, Any]:
    item = item or {}
    payload = {
        "name": item.get("name") or item.get("canonical_name") or item.get("display_name"),
        "kind": item.get("kind") or item.get("place_type") or item.get("type") or item.get("class"),
        "confidence": item.get("confidence"),
        "provider": item.get("provider"),
        "reason": reason,
    }
    if validation:
        payload["validation"] = validation.to_dict()
    if score is not None:
        payload["score"] = round(float(score), 3)
    return payload


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _meaningful_tokens(text: str | None) -> list[str]:
    tokens = re.findall(r"\w+", normalize_vi(text))
    return [token for token in tokens if (token.isdigit() or len(token) > 2) and token not in PLACE_STOPWORDS]


def _candidate_text(item: dict[str, Any]) -> str:
    parts = [item.get("name") or "", item.get("canonical_name") or "", item.get("display_name") or ""]
    aliases = item.get("aliases") or []
    if isinstance(aliases, (list, tuple, set)):
        parts.extend(str(alias) for alias in aliases)
    return " ".join(str(part) for part in parts if part)


def _candidate_head_text(item: dict[str, Any]) -> str:
    display_head = str(item.get("display_name") or "").split(",")[0]
    parts = [item.get("name") or "", item.get("canonical_name") or "", display_head]
    return normalize_vi(" ".join(str(part) for part in parts if part))


def _distinctive_tokens(text: str | None) -> list[str]:
    return [token for token in _meaningful_tokens(text) if token.isdigit() or len(token) >= 4]


def _candidate_matches_known_alias(query: str, item: dict[str, Any]) -> bool:
    try:
        from ..services.place_reference import candidate_matches_known_alias

        return candidate_matches_known_alias(query, item)
    except Exception:
        return True


def _score_value(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("score") or value.get("total")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
