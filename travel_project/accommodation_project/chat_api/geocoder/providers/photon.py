"""
Photon (Komoot) geocoder provider.

Photon (https://photon.komoot.io) is an open-source, OSM-backed geocoder with
*better fuzzy matching and Vietnamese support* than upstream Nominatim:
  - Typeahead-style suggestions ("Bệnh viện Ung Bướu" works)
  - Typo tolerance
  - Multi-language indexing
  - Free, no API key required (be polite; rate-limit politely)

We use Photon as a fallback when:
  1. Local gazetteer (landmarks.json / supported_areas.json) misses
  2. Nominatim returns empty / wrong-region results

Returns the same shape as NominatimProvider.search() — a list of dicts that
include lat/lon/display_name fields — so downstream scoring code can be reused.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from .base import GeocoderProvider, GeocoderQuery, GeocoderViewbox
from ...normalizers import normalize_key

logger = logging.getLogger(__name__)

DEFAULT_PHOTON_URL = "https://photon.komoot.io/api/"
DEFAULT_USER_AGENT = "TravelProjectAccommodation/1.0"

# HCM bounding box — same as Nominatim provider so results stay city-bounded
HCM_VIEWBOX = GeocoderViewbox(
    min_lon=106.30,
    min_lat=10.30,
    max_lon=107.10,
    max_lat=11.20,
)
HCM_HINTS = ("ho chi minh", "hcm", "tphcm", "sai gon", "saigon")


class PhotonProvider(GeocoderProvider):
    """Photon (OSM via Elasticsearch) geocoder.

    Strategy: append city/country context if missing, prefer Vietnamese
    language results, bias by HCM lat/lon center for ranking.
    """

    name = "photon"
    _last_request_at = 0.0

    def __init__(
        self,
        *,
        url: str | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
    ):
        self.url = url or os.getenv("PHOTON_URL", DEFAULT_PHOTON_URL)
        self.user_agent = user_agent or os.getenv("GEOCODER_USER_AGENT", DEFAULT_USER_AGENT)
        self.timeout = timeout if timeout is not None else _timeout_seconds()
        self.min_interval = _rate_limit_seconds()

    # ── Public API (mirrors NominatimProvider) ──────────────────────────────

    def search(self, query: GeocoderQuery) -> list[dict[str, Any]]:
        self._rate_limit()
        params: dict[str, Any] = {
            "q": _with_hcm_context(query.text),
            "limit": query.limit,
            "lang": "default",
        }
        # Bias ranking toward HCM center if viewbox is provided
        if query.viewbox:
            cx = (query.viewbox.min_lon + query.viewbox.max_lon) / 2
            cy = (query.viewbox.min_lat + query.viewbox.max_lat) / 2
            params["lat"] = cy
            params["lon"] = cx
            if query.bounded:
                # bbox = min_lon, min_lat, max_lon, max_lat
                params["bbox"] = (
                    f"{query.viewbox.min_lon},{query.viewbox.min_lat},"
                    f"{query.viewbox.max_lon},{query.viewbox.max_lat}"
                )

        try:
            response = requests.get(
                self.url,
                params=params,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json() or {}
        except requests.RequestException as exc:
            logger.info("photon: request failed for %r: %s", query.text, exc)
            return []

        features = data.get("features") or []
        return [_feature_to_dict(feat) for feat in features if feat]

    def search_place(
        self,
        query: str,
        *,
        city: str = "Hồ Chí Minh",
        country: str = "Vietnam",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self.search(
            GeocoderQuery(
                text=_with_hcm_context(query, city=city, country=country),
                viewbox=HCM_VIEWBOX,
                bounded=False,  # Photon ranks better when *biased* not bounded
                limit=limit,
            )
        )

    # ── Rate limiting (politeness; Photon's docs warn about heavy use) ──────

    def _rate_limit(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self.__class__._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.__class__._last_request_at = time.monotonic()


# ─── Helpers ────────────────────────────────────────────────────────────────

def _timeout_seconds() -> float:
    try:
        return float(os.getenv("PHOTON_TIMEOUT_SECONDS", "4"))
    except (TypeError, ValueError):
        return 4.0


def _rate_limit_seconds() -> float:
    try:
        return float(os.getenv("PHOTON_RATE_LIMIT_SECONDS", "0.3"))
    except (TypeError, ValueError):
        return 0.3


def _with_hcm_context(query: str | None, *, city: str = "Hồ Chí Minh", country: str = "Vietnam") -> str:
    text = " ".join(str(query or "").split())
    norm = normalize_key(text)
    if any(token in norm for token in HCM_HINTS):
        return text
    return f"{text}, {city}, {country}".strip(" ,")


def _feature_to_dict(feat: dict[str, Any]) -> dict[str, Any]:
    """Translate a Photon GeoJSON feature into the dict shape Nominatim returns.

    Downstream scoring code (chat_api/services/geocoder.py) expects:
        lat, lon              — numeric
        display_name          — single-line human label
        name                  — short label
        address (dict)        — house_number, road, suburb, city, country, ...
        class, type           — OSM class/type tags
        importance            — float 0..1 (we synthesize from popularity if absent)
        osm_id, osm_type      — identity
        place_id              — Photon doesn't have it; reuse osm_id
    """
    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or []

    try:
        lon = float(coords[0]) if len(coords) >= 2 else None
        lat = float(coords[1]) if len(coords) >= 2 else None
    except (TypeError, ValueError):
        lat = lon = None

    address = {
        "house_number": props.get("housenumber"),
        "road": props.get("street") or props.get("road"),
        "suburb": props.get("locality") or props.get("district") or props.get("city_district"),
        "city": props.get("city") or props.get("state"),
        "state": props.get("state"),
        "country": props.get("country"),
        "postcode": props.get("postcode"),
    }
    # Drop None values for cleanliness
    address = {k: v for k, v in address.items() if v}

    display_parts = [
        props.get("name"),
        props.get("street"),
        props.get("housenumber"),
        props.get("city") or props.get("state"),
        props.get("country"),
    ]
    display_name = ", ".join(str(part) for part in display_parts if part)

    return {
        "lat": lat,
        "lon": lon,
        "display_name": display_name or props.get("name") or "",
        "name": props.get("name"),
        "address": address,
        "class": props.get("osm_key"),
        "type": props.get("osm_value"),
        "importance": float(props.get("importance") or 0.5),
        "osm_id": props.get("osm_id"),
        "osm_type": props.get("osm_type"),
        "place_id": props.get("osm_id"),
    }
