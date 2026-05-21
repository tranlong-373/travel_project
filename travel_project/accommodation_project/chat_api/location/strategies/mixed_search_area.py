"""
MixedSearchAreaFallbackStrategy — area fallback for mixed_search queries.

For compound queries like "resort gần biển Đà Nẵng 3 ngày 2 đêm" where the
landmark is not in the static JSON and the geocoder fails, use the area_hint
detected by the classifier as the search area.

Fires after LandmarkStaticJsonStrategy (order=55) and FallbackGeocodeStrategy
(order=60), just before PoiCentroidStrategy (order=70). Needs order=62 so it
fires after geocoding is attempted but before AmbiguousOrUnsupportedStrategy.
"""
from __future__ import annotations

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy


class MixedSearchAreaFallbackStrategy(LocationStrategy):
    order = 62
    name = "mixed_search_area_fallback"

    def can_handle(self, context: LocationContext) -> bool:
        return context.input_kind == "mixed_search" and bool(context.area_hint)

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        area = context.area_hint
        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.AREA,
            raw_phrase=context.location_phrase or context.raw_text,
            canonical_area=area,
            display_label=area,
            latitude=None,
            longitude=None,
            radius_km=10.0,
            provider="area_hint_fallback",
            cache_hit=False,
            debug={"source": "mixed_search_area_fallback", "area_hint": area},
        )
