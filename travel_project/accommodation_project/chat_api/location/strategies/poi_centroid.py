"""
PoiCentroidStrategy — handles generic_poi_in_area queries.

For queries like "gần quán cafe ở Quận 5" or "gần bệnh viện ở Phú Nhuận",
we search for accommodation IN the named area with the POI category noted as a
soft constraint. The area centroid (from PlaceReference or gazetteer) is used
as the search anchor with mode=AREA.

Resolution order:
  1. PlaceReference cache lookup for area_hint
  2. If no cached centroid: return area mode without lat/lon (recommendation
     engine falls back to area-name filtering)
"""
from __future__ import annotations

import logging
from typing import Any

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)


def _lookup_area_centroid(area: str | None) -> dict[str, Any] | None:
    """
    Look up area centroid from PlaceReference.
    Wrapped for testability — patch this function in tests.
    """
    if not area:
        return None
    try:
        from ...services.place_reference import find_place_reference
        return find_place_reference(area)
    except Exception as exc:
        logger.debug("poi_centroid: place_reference lookup failed for %r: %s", area, exc)
        return None


class PoiCentroidStrategy(LocationStrategy):
    order = 70
    name = "poi_centroid"

    def can_handle(self, context: LocationContext) -> bool:
        return context.input_kind == "generic_poi_in_area" and bool(context.area_hint)

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        area = context.area_hint
        ref = _lookup_area_centroid(area)

        lat: float | None = None
        lon: float | None = None
        radius_km = 10.0
        cache_hit = False

        if ref:
            raw_lat = ref.get("latitude") or ref.get("lat")
            raw_lon = ref.get("longitude") or ref.get("lon")
            if raw_lat is not None and raw_lon is not None:
                lat = float(raw_lat)
                lon = float(raw_lon)
                radius_km = float(ref.get("default_radius_km") or 10.0)
                cache_hit = True

        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.AREA,
            raw_phrase=context.location_phrase or context.raw_text,
            canonical_area=area,
            display_label=ref.get("display_name") if ref else area,
            # Centroid coords are optional — recommendation engine uses area name if None
            latitude=lat,
            longitude=lon,
            radius_km=radius_km,
            # Store POI category as nearby_poi_label for soft-filter downstream
            nearby_poi_key=context.poi_category,
            nearby_poi_label=context.location_phrase,
            provider="place_reference_centroid" if cache_hit else "area_fallback",
            cache_hit=cache_hit,
            debug={
                "area": area,
                "poi_category": context.poi_category,
                "centroid_found": cache_hit,
            },
        )
