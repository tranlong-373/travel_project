from __future__ import annotations

import os
from typing import Any

import requests

from ...normalizers import normalize_key


GEOAPIFY_URL = "https://api.geoapify.com/v1/geocode/search"
HCM_HINTS = ("ho chi minh", "hcm", "tphcm", "sai gon", "saigon")


def search_place(query: str, *, city: str = "Hồ Chí Minh", country: str = "Vietnam", limit: int = 5) -> list[dict[str, Any]]:
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        return []
    text = _with_city(query, city=city, country=country)
    try:
        response = requests.get(
            GEOAPIFY_URL,
            params={
                "text": text,
                "apiKey": api_key,
                "limit": limit,
                "lang": "vi",
                "filter": "rect:106.30,11.20,107.10,10.30",
                "bias": "proximity:106.7009,10.7769",
            },
            headers={"User-Agent": os.getenv("GEOCODER_USER_AGENT", "travel_project_dev_contact_email")},
            timeout=_timeout_seconds(),
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    candidates: list[dict[str, Any]] = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        lon, lat = _coordinates(feature)
        candidates.append(
            {
                "name": props.get("name") or props.get("formatted") or query,
                "display_name": props.get("formatted") or props.get("address_line2") or props.get("name") or query,
                "lat": lat,
                "lon": lon,
                "lng": lon,
                "address": props,
                "district": props.get("district") or props.get("suburb"),
                "city": props.get("city") or props.get("county"),
                "country": props.get("country"),
                "kind": props.get("result_type") or props.get("category") or "geocoded",
                "provider": "geoapify",
                "provider_place_id": props.get("place_id") or props.get("datasource", {}).get("raw", {}).get("osm_id") or "",
                "raw": feature,
                "raw_payload": feature,
                "confidence": float(props.get("rank", {}).get("confidence") or 0.0),
            }
        )
    return candidates


def _with_city(query: str | None, *, city: str, country: str) -> str:
    text = " ".join(str(query or "").split())
    norm = normalize_key(text)
    if any(token in norm for token in HCM_HINTS):
        return text
    return f"{text}, {city}, {country}".strip(" ,")


def _coordinates(feature: dict[str, Any]) -> tuple[float | None, float | None]:
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") or []
    try:
        if len(coords) >= 2:
            return float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None, None
    return None, None


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("GEOCODER_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        return 8.0
