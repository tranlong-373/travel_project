from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..normalizers import normalize_key
from .providers.nominatim import HCM_VIEWBOX


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "inside_hcm": self.inside_hcm,
            "address_matches_hcm": self.address_matches_hcm,
            "category": self.category,
            "lat": self.lat,
            "lon": self.lon,
        }


def validate_geocode_candidate(
    item: dict[str, Any] | None,
    *,
    explicit_venue: bool = False,
) -> GeocodeValidation:
    item = item or {}
    lat = _float_or_none(item.get("lat") if item.get("lat") is not None else item.get("latitude"))
    lon = _float_or_none(item.get("lon") if item.get("lon") is not None else item.get("longitude"))
    category = geocode_category(item)
    inside_hcm = is_inside_hcm(lat, lon)
    address_matches = address_mentions_hcm(item)

    if lat is None or lon is None:
        return GeocodeValidation(False, "missing_coordinates", False, address_matches, category, lat, lon)
    if not inside_hcm:
        return GeocodeValidation(False, "outside_hcm", False, address_matches, category, lat, lon)
    if category in BLOCKED_POI_CATEGORIES and not explicit_venue:
        return GeocodeValidation(False, f"blocked_category:{category}", inside_hcm, address_matches, category, lat, lon)
    return GeocodeValidation(True, "ok", inside_hcm, address_matches, category, lat, lon)


def is_inside_hcm(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return (
        HCM_VIEWBOX.min_lat <= float(lat) <= HCM_VIEWBOX.max_lat
        and HCM_VIEWBOX.min_lon <= float(lon) <= HCM_VIEWBOX.max_lon
    )


def address_mentions_hcm(item: dict[str, Any]) -> bool:
    haystack_parts = [item.get("display_name") or "", item.get("name") or "", item.get("canonical_name") or ""]
    address = item.get("address") or {}
    if isinstance(address, dict):
        haystack_parts.extend(str(value) for value in address.values() if value)
    haystack = normalize_key(" ".join(haystack_parts))
    return any(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", haystack) for token in HCM_ADDRESS_TOKENS)


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

