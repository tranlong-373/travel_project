from __future__ import annotations

import os
from typing import Any

import requests

from ...normalizers import normalize_key


FOURSQUARE_URL = "https://api.foursquare.com/v3/places/search"
HCM_HINTS = ("ho chi minh", "hcm", "tphcm", "sai gon", "saigon")


def search_place(query: str, *, city: str = "Hồ Chí Minh", country: str = "Vietnam", limit: int = 5) -> list[dict[str, Any]]:
    api_key = os.getenv("FOURSQUARE_API_KEY", "").strip()
    if not api_key:
        return []
    text = _with_city(query, city=city, country=country)
    try:
        response = requests.get(
            FOURSQUARE_URL,
            params={
                "query": text,
                "near": f"{city}, {country}",
                "limit": limit,
                "sort": "RELEVANCE",
            },
            headers={
                "Authorization": api_key,
                "Accept": "application/json",
                "User-Agent": os.getenv("GEOCODER_USER_AGENT", "travel_project_dev_contact_email"),
            },
            timeout=_timeout_seconds(),
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    candidates: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        geocodes = item.get("geocodes") or {}
        main = geocodes.get("main") or {}
        location = item.get("location") or {}
        categories = item.get("categories") or []
        category = categories[0].get("name") if categories and isinstance(categories[0], dict) else "geocoded"
        candidates.append(
            {
                "name": item.get("name") or query,
                "display_name": location.get("formatted_address") or item.get("name") or query,
                "lat": main.get("latitude"),
                "lon": main.get("longitude"),
                "lng": main.get("longitude"),
                "address": location,
                "district": location.get("locality") or location.get("neighborhood"),
                "city": location.get("locality") or city,
                "country": location.get("country") or country,
                "kind": normalize_key(category) or "geocoded",
                "provider": "foursquare",
                "provider_place_id": item.get("fsq_id") or "",
                "raw": item,
                "raw_payload": item,
                "confidence": 0.82,
            }
        )
    return candidates


def _with_city(query: str | None, *, city: str, country: str) -> str:
    text = " ".join(str(query or "").split())
    norm = normalize_key(text)
    if any(token in norm for token in HCM_HINTS):
        return text
    return f"{text}, {city}, {country}".strip(" ,")


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("GEOCODER_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        return 8.0
