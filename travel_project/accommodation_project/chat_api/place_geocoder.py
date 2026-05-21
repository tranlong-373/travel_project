from __future__ import annotations

import re
from typing import Any

from .geocoder.validator import (
    rejected_geocoder_payload as validator_rejected_geocoder_payload,
    validate_geocode_candidate,
)
from .location_gazetteer import generate_location_aliases, load_supported_locations
from .normalizers import normalize_common_typos, normalize_key
from .slot_pipeline import is_ambiguous_location_phrase, is_blocked_location_phrase

DEFAULT_PLACE_RADIUS_KM = 5.0
DEFAULT_PLACE_CONTEXT = "Hồ Chí Minh, Việt Nam"
GEOCODER_PROVIDER = "osm_nominatim"

_CONTEXT_HINTS = (
    "viet nam",
    "vietnam",
    "ho chi minh",
    "hcm",
    "tphcm",
    "tp hcm",
    "sai gon",
    "saigon",
    "ha noi",
    "hanoi",
    "da nang",
    "da lat",
)
_GENERIC_NEAR_ANCHORS = {
    "bien",
    "beach",
    "gan bien",
    "near beach",
    "trung tam",
    "trung",
    "center",
    "centre",
    "downtown",
    "khu trung tam",
    "safe area",
    "khu an toan",
}
_REJECTED_POI_TYPES = {
    "cafe",
    "restaurant",
    "shop",
    "bar",
    "pub",
    "fast_food",
    "temple",
    "place_of_worship",
    "company",
    "business",
}
_CITY_CENTER_REJECT_TYPES = _REJECTED_POI_TYPES | {"tourism", "attraction", "monument", "museum"}
_PLACE_STOPWORDS = {
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
    "pho",
    "duong",
    "du",
    "lich",
    "khu",
    "cho",
    "nha",
    "tho",
    "di",
    "bo",
    "tp",
    "thanh",
    "pho",
    "viet",
    "nam",
    "toi",
    "minh",
    "tui",
    "em",
    "anh",
    "chi",
    "muon",
    "can",
    "tim",
    "kiem",
    "tin",
    "co",
    "thue",
    "dat",
    "book",
    "booking",
    "reserve",
    "giup",
    "goi",
    "y",
}


def should_geocode_place_phrase(place_name: str | None) -> bool:
    norm = normalize_key(normalize_common_typos(place_name or ""))
    norm = re.sub(r"[^\w\s]", " ", norm, flags=re.UNICODE)
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return False
    if is_blocked_location_phrase(norm):
        return False
    if is_ambiguous_location_phrase(norm):
        return False
    if any(norm == generic or norm.startswith(f"{generic} ") for generic in _GENERIC_NEAR_ANCHORS):
        return False
    return bool(_meaningful_tokens(norm))


def build_place_geocode_query(place_name: str) -> str:
    text = " ".join(str(place_name or "").split())
    norm = normalize_key(text)
    if any(hint in norm for hint in _CONTEXT_HINTS):
        return text
    return f"{text}, {DEFAULT_PLACE_CONTEXT}"


def resolve_place_reference(place_name: str | None, *, default_radius_km: float = DEFAULT_PLACE_RADIUS_KM) -> dict[str, Any] | None:
    if not should_geocode_place_phrase(place_name):
        return None

    try:
        from .services.geocoder import geocode_place

        result = geocode_place(str(place_name), city_hint=DEFAULT_PLACE_CONTEXT)
    except Exception:
        return None

    if not result.success:
        return None

    payload = result.to_dict()
    payload["name"] = payload.get("canonical_name") or payload.get("display_name") or str(place_name)
    payload["kind"] = payload.get("place_type") or "geocoded"
    payload["lat"] = payload.get("latitude")
    payload["lon"] = payload.get("longitude")
    payload["query"] = payload.get("query_used")
    if default_radius_km != DEFAULT_PLACE_RADIUS_KM:
        payload["default_radius_km"] = default_radius_km
    return payload


def get_cached_place_reference(place_name: str | None) -> dict[str, Any] | None:
    try:
        from .services.geocoder import get_cached_place_reference as get_cached
    except Exception:
        return None
    return get_cached(place_name)


def save_place_reference(payload: dict[str, Any]) -> None:
    try:
        from .services.geocoder import save_place_reference as save
    except Exception:
        return
    save(payload)


def validate_geocoded_place(
    geocoded: dict[str, Any] | None,
    *,
    intent: str = "landmark",
    query: str | None = None,
) -> bool:
    if not geocoded:
        return False
    validation = validate_geocode_candidate(geocoded, query=query, intent=intent)
    if not validation.accepted:
        return False
    kind = normalize_key(str(geocoded.get("kind") or geocoded.get("place_type") or ""))
    confidence = _float_or_none(geocoded.get("confidence"))
    if confidence is not None and confidence < 0.75:
        return False
    if intent == "city_center":
        return kind not in _CITY_CENTER_REJECT_TYPES
    if intent == "airport":
        return any(token in kind for token in ("airport", "aerodrome")) or "san bay" in normalize_key(str(geocoded.get("name") or ""))
    if intent == "university":
        return any(token in kind for token in ("university", "school", "college")) or "dai hoc" in normalize_key(str(geocoded.get("name") or ""))
    return kind not in _REJECTED_POI_TYPES


def rejected_geocoder_payload(geocoded: dict[str, Any] | None, *, reason: str) -> dict[str, Any]:
    validation = validate_geocode_candidate(geocoded or {})
    return validator_rejected_geocoder_payload(geocoded, reason=reason or validation.reason, validation=validation)


def _reference_to_payload(reference) -> dict[str, Any]:
    address = reference.address or {}
    return {
        "name": reference.canonical_name,
        "canonical_name": reference.canonical_name,
        "normalized_name": reference.normalized_name,
        "aliases": list(reference.aliases or []),
        "kind": reference.kind,
        "lat": reference.latitude,
        "lon": reference.longitude,
        "default_radius_km": reference.default_radius_km,
        "provider": reference.provider,
        "provider_place_id": reference.provider_place_id,
        "query": reference.query,
        "display_name": reference.display_name or reference.canonical_name,
        "address": address,
        "raw_payload": reference.raw_payload or {},
        "map_area": _area_from_address(address),
        "confidence": reference.confidence,
    }


def _normalized_place_name(place_name: str | None) -> str:
    return normalize_key(place_name or "")


def _display_place_name(place_name: str, geocoded: dict[str, Any]) -> str:
    display = str(geocoded.get("display_name") or "").split(",")[0].strip()
    return display or place_name


def _is_specific_place_match(place_name: str, geocoded: dict[str, Any]) -> bool:
    haystack_parts = [geocoded.get("display_name") or ""]
    address = geocoded.get("address") or {}
    if isinstance(address, dict):
        haystack_parts.extend(str(value) for value in address.values() if value)
    haystack = normalize_key(" ".join(haystack_parts))
    tokens = _meaningful_tokens(place_name)
    if not tokens:
        return False
    return any(token in haystack for token in tokens)


def _meaningful_tokens(text: str | None) -> list[str]:
    norm = normalize_key(text or "")
    tokens = re.findall(r"\w+", norm)
    return [token for token in tokens if (token.isdigit() or len(token) > 2) and token not in _PLACE_STOPWORDS]


def _area_from_address(address: dict[str, Any]) -> str | None:
    if not isinstance(address, dict):
        return None
    fields = ("city_district", "district", "borough", "suburb", "town", "city", "municipality", "state")
    for field in fields:
        value = address.get(field)
        area = _supported_area_from_text(str(value or ""))
        if area:
            return area
    return None


def _supported_area_from_text(value: str) -> str | None:
    key = normalize_key(value)
    if not key:
        return None
    for location in load_supported_locations():
        aliases = [location.get("canonical_name") or "", *(location.get("aliases") or [])]
        if any(normalize_key(alias) == key for alias in aliases):
            return location.get("canonical_name")
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
