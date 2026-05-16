from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from .normalizers import normalize_key


@dataclass(frozen=True)
class CityCenter:
    canonical_city: str
    display_label: str
    aliases: tuple[str, ...]
    lat: float
    lon: float
    default_radius_km: float = 4.0


CITY_CENTERS: tuple[CityCenter, ...] = (
    CityCenter(
        canonical_city="TP HCM",
        display_label="Trung tâm TP.HCM",
        aliases=(
            "tp hcm",
            "tphcm",
            "hcm",
            "ho chi minh",
            "ho chi minh city",
            "hồ chí minh",
            "tp hồ chí minh",
            "sài gòn",
            "sai gon",
            "saigon",
        ),
        lat=10.7758,
        lon=106.7004,
        default_radius_km=4.0,
    ),
    CityCenter(
        canonical_city="Hà Nội",
        display_label="Trung tâm Hà Nội",
        aliases=("hà nội", "ha noi", "hanoi"),
        lat=21.0287,
        lon=105.8520,
        default_radius_km=4.0,
    ),
    CityCenter(
        canonical_city="Đà Lạt",
        display_label="Trung tâm Đà Lạt",
        aliases=("đà lạt", "da lat"),
        lat=11.9404,
        lon=108.4372,
        default_radius_km=4.0,
    ),
)

CITY_CENTER_PATTERNS: tuple[str, ...] = (
    r"\btrung\s+tam\s+thanh\s+pho\b",
    r"\btrung\s+tam\s+tp\b",
    r"\bkhu\s+trung\s+tam\b",
    r"\bgan\s+trung\s+tam\b",
    r"\btrung\s+tam\b",
    r"\bdowntown\b",
    r"\bcity\s+center\b",
    r"\bcity\s+centre\b",
)


def detect_city_center_intent(text: str | None) -> dict[str, Any] | None:
    norm = normalize_key(text or "")
    if not norm or not any(re.search(pattern, norm) for pattern in CITY_CENTER_PATTERNS):
        return None

    city = city_hint_from_text(norm) or default_search_city()
    if city:
        center = resolve_city_center(city)
        if center:
            return {
                "should_resolve": False,
                "candidate": "trung tâm thành phố",
                "resolve_text": "trung tâm thành phố",
                "confidence": 0.93,
                "reason": "abstract_city_center_location",
                "mode_hint": "city_center",
                "city_hint": center["canonical_area"],
                "city_center": center,
            }

    return {
        "should_resolve": False,
        "candidate": "trung tâm thành phố",
        "resolve_text": "trung tâm thành phố",
        "confidence": 0.72,
        "reason": "needs_city_for_city_center",
        "mode_hint": "city_center",
        "needs_city_clarification": True,
        "city_center": None,
    }


def resolve_city_center(city: str | None) -> dict[str, Any] | None:
    center = _city_center_for(city)
    if center is None:
        return None
    return {
        "canonical_area": center.canonical_city,
        "location_display_label": center.display_label,
        "anchor_name": center.display_label,
        "anchor_kind": "city_center",
        "anchor_lat": center.lat,
        "anchor_lon": center.lon,
        "anchor_radius_km": center.default_radius_km,
        "default_radius_km": center.default_radius_km,
        "provider": "semantic",
        "location_source": "semantic_city_center",
        "confidence": 0.93,
    }


def city_hint_from_text(text: str | None) -> str | None:
    norm = normalize_key(text or "")
    if not norm:
        return None
    for center in CITY_CENTERS:
        for alias in center.aliases:
            alias_key = normalize_key(alias)
            if alias_key and re.search(rf"(?<!\w){re.escape(alias_key)}(?!\w)", norm):
                return center.canonical_city
    return None


def default_search_city() -> str | None:
    value = getattr(settings, "DEFAULT_SEARCH_CITY", None)
    if value is None:
        value = os.getenv("DEFAULT_SEARCH_CITY", "TP HCM")
    value = str(value).strip()
    if not value:
        return None
    center = _city_center_for(value)
    return center.canonical_city if center else None


def _city_center_for(city: str | None) -> CityCenter | None:
    key = normalize_key(city or "")
    if not key:
        return None
    for center in CITY_CENTERS:
        if key == normalize_key(center.canonical_city):
            return center
        if any(key == normalize_key(alias) for alias in center.aliases):
            return center
    return None
