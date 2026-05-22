"""
NearAnchorFromPlaceReferenceStrategy — PlaceReference DB cache lookup.

Checks the PlaceReference cache BEFORE calling any external geocoder.
On cache hit: returns near_anchor with stored coordinates (fast, no API cost).
On cache miss: returns None → FallbackGeocodeStrategy takes over.

Handles:
  - landmark_or_poi   → "gần Landmark 81", "gần Dinh Độc Lập"
  - specific_address  → "1 Sư Vạn Hạnh, Phường 9, Quận 5"
  - mixed_search      → when location_phrase is extractable
"""
from __future__ import annotations

import logging
from typing import Any

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)

# input_kinds this strategy handles
_HANDLED_KINDS: frozenset[str] = frozenset({
    "landmark_or_poi",
    "specific_address",
    "mixed_search",
})


def _lookup_place_reference(phrase: str | None) -> dict[str, Any] | None:
    """
    PlaceReference cache lookup.
    Wrapped for testability — patch this function in tests.
    """
    if not phrase:
        return None
    try:
        from ...services.place_reference import find_place_reference
        return find_place_reference(phrase)
    except Exception as exc:
        logger.debug("near_anchor: place_reference lookup failed for %r: %s", phrase, exc)
        return None


def _ref_to_resolved(
    ref: dict[str, Any],
    *,
    raw_phrase: str | None = None,
) -> ResolvedLocation:
    lat = ref.get("latitude") or ref.get("lat")
    lon = ref.get("longitude") or ref.get("lon")
    # Use canonical_name as the short display label — the full OSM display_name
    # may contain wrong administrative text (e.g. "Thành phố Thủ Đức") for streets
    # that are actually inside the inner-city districts.
    short_name = ref.get("canonical_name") or ref.get("name")
    return ResolvedLocation(
        status=LocationStatus.OK,
        mode=LocationMode.NEAR_ANCHOR,
        raw_phrase=raw_phrase,
        canonical_area=ref.get("canonical_name") or ref.get("display_name"),
        display_label=short_name or ref.get("display_name"),
        anchor_name=short_name,
        anchor_kind=ref.get("kind") or ref.get("place_type"),
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        radius_km=float(ref.get("default_radius_km") or 5.0),
        provider=ref.get("provider") or "cache",
        cache_hit=True,
        debug={"source": "place_reference_cache"},
    )


class NearAnchorFromPlaceReferenceStrategy(LocationStrategy):
    order = 50
    name = "near_anchor_from_place_reference"

    def can_handle(self, context: LocationContext) -> bool:
        return (
            context.input_kind in _HANDLED_KINDS
            and bool(context.location_phrase or context.area_hint)
        )

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        phrase = context.location_phrase or context.area_hint
        ref = _lookup_place_reference(phrase)
        if ref is None:
            return None  # cache miss — pass to FallbackGeocodeStrategy

        lat = ref.get("latitude") or ref.get("lat")
        lon = ref.get("longitude") or ref.get("lon")
        if lat is None or lon is None:
            return None  # cached but no usable coordinates

        return _ref_to_resolved(ref, raw_phrase=phrase)
