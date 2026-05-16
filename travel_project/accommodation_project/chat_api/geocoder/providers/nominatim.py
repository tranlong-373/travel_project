from __future__ import annotations

import os
from typing import Any

import requests

from .base import GeocoderProvider, GeocoderQuery, GeocoderViewbox


DEFAULT_OSM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "travel_project_dev_contact_email"
HCM_VIEWBOX = GeocoderViewbox(
    min_lon=106.35,
    min_lat=10.33,
    max_lon=107.05,
    max_lat=11.18,
)


class NominatimProvider(GeocoderProvider):
    name = "osm"

    def __init__(self, *, url: str | None = None, user_agent: str | None = None, timeout: float | None = None):
        self.url = url or os.getenv("OSM_NOMINATIM_URL", DEFAULT_OSM_URL)
        self.user_agent = user_agent or os.getenv("GEOCODER_USER_AGENT", DEFAULT_USER_AGENT)
        self.timeout = timeout if timeout is not None else _timeout_seconds()

    def search(self, query: GeocoderQuery) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "q": query.text,
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


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("GEOCODER_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        return 8.0

