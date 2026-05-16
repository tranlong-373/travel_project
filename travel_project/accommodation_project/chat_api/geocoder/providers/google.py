from __future__ import annotations

from .base import GeocoderProvider, GeocoderQuery


class GoogleGeocoderProvider(GeocoderProvider):
    name = "google"

    def search(self, query: GeocoderQuery) -> list[dict]:
        raise NotImplementedError("Google geocoder provider is not configured for this project yet.")

