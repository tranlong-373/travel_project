"""
Thin wrapper around chat_api.services.geocoder for street-level address resolution.

Provides a simple interface: geocode_street_address(query) -> (lat, lon) | None
- Checks PlaceReference DB cache before calling Nominatim (zero API cost on repeat)
- Rate limiting enforced by NominatimProvider (respects Nominatim policy: max ~2 req/sec)
- Returns None on failure (never raises)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def geocode_street_address(
    query: str,
    *,
    city_hint: str | None = "Việt Nam",
) -> tuple[float, float] | None:
    """
    Resolve a street/address phrase to (latitude, longitude).

    Checks DB cache first — only calls Nominatim if no cached result exists.
    Returns None if resolution fails or coordinates are missing.
    """
    if not query or not query.strip():
        return None

    try:
        from .services.geocoder import geocode_place, get_cached_place_reference

        # Check cache without calling Nominatim
        cached = get_cached_place_reference(query)
        if cached:
            lat = cached.get("latitude") or cached.get("lat")
            lon = cached.get("longitude") or cached.get("lon")
            if lat is not None and lon is not None:
                logger.debug("nominatim_geocoder: cache hit for %r", query)
                return float(lat), float(lon)

        # Cache miss — Nominatim rate limit enforced by NominatimProvider
        result = geocode_place(query, city_hint=city_hint)
        if result.success and result.latitude is not None and result.longitude is not None:
            return result.latitude, result.longitude

        logger.info(
            "nominatim_geocoder: no result for %r — reason=%r queries=%r",
            query,
            result.unresolved_reason or "geocode_place returned success=False",
            list(result.geocoder_queries),
        )

    except Exception as exc:
        logger.warning("nominatim_geocoder: exception for %r: %s", query, exc)

    return None
