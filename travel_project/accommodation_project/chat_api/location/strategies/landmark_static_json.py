"""
LandmarkStaticJsonStrategy — resolve known landmarks from a static JSON file.

Handles landmark_or_poi and mixed_search queries by matching the location_phrase
against the aliases in data/landmarks.json. Returns near_anchor:ok with the
parent area's canonical name.

Fires after NearAnchorFromPlaceReferenceStrategy (order=50) and before
FallbackGeocodeStrategy (order=60). This covers cases where the PlaceReference
DB is empty but the landmark is listed in the static JSON.

No coordinates are available (landmarks.json has names only), so recommendation
engine will use canonical_area for area-name filtering.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ...normalizers import normalize_key
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_HANDLED_KINDS: frozenset[str] = frozenset({
    "landmark_or_poi",
    "mixed_search",
})


DEFAULT_LANDMARK_RADIUS_KM = 3.0


@lru_cache(maxsize=1)
def _load_landmark_index() -> list[tuple[str, str, str, float | None, float | None, float]]:
    """
    Returns list of (normalized_alias, landmark_name, parent_area_canonical, lat, lon, radius_km)
    sorted by alias length descending for greedy matching.
    """
    try:
        landmarks = json.loads((DATA_DIR / "landmarks.json").read_text(encoding="utf-8"))
        areas_raw = json.loads((DATA_DIR / "supported_areas.json").read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("landmark_static_json: failed to load data files: %s", exc)
        return []

    area_by_id: dict[str, str] = {
        area["id"]: area.get("canonical_name") or area["id"].replace("_", " ")
        for area in areas_raw
    }

    entries: list[tuple[str, str, str, float | None, float | None, float]] = []
    for landmark in landmarks:
        name = landmark.get("name", "")
        parent_id = landmark.get("parent_area_id", "")
        canonical_area = area_by_id.get(parent_id, parent_id)
        lat = landmark.get("lat")
        lon = landmark.get("lon")
        radius_km = float(landmark.get("radius_km") or DEFAULT_LANDMARK_RADIUS_KM)
        for alias in landmark.get("aliases", []):
            norm_alias = normalize_key(alias)
            if norm_alias:
                entries.append((norm_alias, name, canonical_area, lat, lon, radius_km))

    # Longest alias first — greedy match avoids "ben thanh" shadowing "cho ben thanh"
    entries.sort(key=lambda t: len(t[0]), reverse=True)
    return entries


def _find_landmark(phrase: str | None) -> tuple[str, str, float | None, float | None, float] | None:
    """
    Return (landmark_name, canonical_area, lat, lon, radius_km) if phrase contains a known alias.
    Uses substring match so mixed_search location_phrases (e.g. "landmark 81
    duoi 1tr5 cho 2 nguoi") still resolve correctly.
    Returns None if no match.
    """
    if not phrase:
        return None
    norm = normalize_key(phrase)
    if not norm:
        return None
    for alias, name, canonical_area, lat, lon, radius_km in _load_landmark_index():
        if alias in norm:
            return name, canonical_area, lat, lon, radius_km
    return None


class LandmarkStaticJsonStrategy(LocationStrategy):
    order = 55
    name = "landmark_static_json"

    def can_handle(self, context: LocationContext) -> bool:
        return (
            context.input_kind in _HANDLED_KINDS
            and bool(context.location_phrase)
        )

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        match = _find_landmark(context.location_phrase)
        if match is None:
            return None

        landmark_name, canonical_area, lat, lon, radius_km = match
        has_coords = lat is not None and lon is not None
        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.NEAR_ANCHOR,
            raw_phrase=context.location_phrase,
            canonical_area=canonical_area,
            display_label=landmark_name,
            anchor_name=landmark_name,
            anchor_kind="landmark",
            latitude=lat,
            longitude=lon,
            radius_km=radius_km,
            provider="landmark_static_json",
            cache_hit=has_coords,
            debug={
                "source": "landmark_static_json",
                "matched": landmark_name,
                "has_coords": has_coords,
            },
        )
