from __future__ import annotations

import os
import time
from typing import Any

import requests

from .base import GeocoderProvider, GeocoderQuery, GeocoderViewbox
from ...normalizers import normalize_key


DEFAULT_OSM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "travel_project_dev_contact_email"
HCM_VIEWBOX = GeocoderViewbox(
    min_lon=106.30,
    min_lat=10.30,
    max_lon=107.10,
    max_lat=11.20,
)
HCM_HINTS = ("ho chi minh", "hcm", "tphcm", "sai gon", "saigon")


class NominatimProvider(GeocoderProvider):
    name = "osm"
    _last_request_at = 0.0

    def __init__(self, *, url: str | None = None, user_agent: str | None = None, timeout: float | None = None):
        self.url = url or os.getenv("OSM_NOMINATIM_URL", DEFAULT_OSM_URL)
        self.user_agent = user_agent or os.getenv("GEOCODER_USER_AGENT", DEFAULT_USER_AGENT)
        self.timeout = timeout if timeout is not None else _timeout_seconds()
        self.min_interval = _rate_limit_seconds()

    def search(self, query: GeocoderQuery) -> list[dict[str, Any]]:
        self._rate_limit()
        params: dict[str, Any] = {
            "q": _with_hcm_context(query.text),
            "format": "json",
            "limit": query.limit,
            "addressdetails": 1,
            "countrycodes": "vn",
            "accept-language": "vi,en",
        }
        if query.viewbox:
            params["viewbox"] = query.viewbox.to_nominatim()
            params["bounded"] = 1 if query.bounded else 0

        response = requests.get(
            self.url,
            params=params,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def search_place(self, query: str, *, city: str = "Hồ Chí Minh", country: str = "Vietnam", limit: int = 5) -> list[dict[str, Any]]:
        return self.search(GeocoderQuery(text=_with_hcm_context(query, city=city, country=country), viewbox=HCM_VIEWBOX, bounded=True, limit=limit))

    def _rate_limit(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self.__class__._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.__class__._last_request_at = time.monotonic()


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("GEOCODER_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        return 8.0


def _rate_limit_seconds() -> float:
    try:
        return float(os.getenv("NOMINATIM_RATE_LIMIT_SECONDS", "1.0"))
    except (TypeError, ValueError):
        return 1.0


def _with_hcm_context(query: str | None, *, city: str = "Hồ Chí Minh", country: str = "Vietnam") -> str:
    text = " ".join(str(query or "").split())
    norm = normalize_key(text)
    if any(token in norm for token in HCM_HINTS):
        return text
    return f"{text}, {city}, {country}".strip(" ,")
