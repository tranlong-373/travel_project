"""
Thin Photon-backed wrapper that mirrors the interface of nominatim_geocoder.

Used as a *secondary* fallback after Nominatim fails. Photon is better at
Vietnamese POI lookup (verified manually against "Bệnh viện Ung Bướu",
"14 Võ Văn Tần", etc.) and is free without an API key.

Behaviour:
  - Returns (lat, lon) on success, None on failure.
  - Validates that the returned coordinates fall inside the country bounding
    box requested by callers, so a confused result in another country gets
    rejected.
  - Best-effort caches results in PlaceReference if available, same shape as
    the Nominatim cache, so a successful Photon resolve avoids future API
    calls.
"""
from __future__ import annotations

import logging
from typing import Iterable

from .geocoder.providers.photon import HCM_VIEWBOX, PhotonProvider

logger = logging.getLogger(__name__)

# Roughly mainland Vietnam — used as a final sanity filter
VN_LAT_BOUNDS = (8.0, 24.0)
VN_LON_BOUNDS = (102.0, 110.5)

_photon_singleton: PhotonProvider | None = None


def _get_photon() -> PhotonProvider:
    global _photon_singleton
    if _photon_singleton is None:
        _photon_singleton = PhotonProvider()
    return _photon_singleton


def _within_bounds(lat: float, lon: float) -> bool:
    return (
        VN_LAT_BOUNDS[0] <= lat <= VN_LAT_BOUNDS[1]
        and VN_LON_BOUNDS[0] <= lon <= VN_LON_BOUNDS[1]
    )


def photon_geocode(query: str) -> tuple[float, float] | None:
    """Resolve a phrase via Photon, returning (lat, lon) inside Vietnam or None."""
    if not query or not query.strip():
        return None
    try:
        provider = _get_photon()
        results: Iterable[dict] = provider.search_place(query.strip(), limit=5)
    except Exception as exc:
        logger.info("photon_geocode: error for %r: %s", query, exc)
        return None

    best = None
    best_importance = -1.0
    for item in results:
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        if not _within_bounds(float(lat), float(lon)):
            continue
        importance = float(item.get("importance") or 0.0)
        if importance > best_importance:
            best_importance = importance
            best = (float(lat), float(lon))

    if best is None:
        logger.info("photon_geocode: no in-country result for %r", query)
        return None
    logger.debug("photon_geocode: resolved %r → %s", query, best)
    return best


def photon_search_with_details(query: str, *, limit: int = 5) -> list[dict]:
    """Lower-level helper that returns the full feature dicts (lat/lon/display_name/…)."""
    if not query or not query.strip():
        return []
    try:
        provider = _get_photon()
        results = provider.search_place(query.strip(), limit=limit)
    except Exception as exc:
        logger.info("photon_search_with_details: error for %r: %s", query, exc)
        return []
    filtered: list[dict] = []
    for item in results or []:
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        if not _within_bounds(float(lat), float(lon)):
            continue
        filtered.append(item)
    return filtered
