"""
DirectAreaStrategy — handles area-only queries.

When the user specifies only a district/city with no landmark or coordinates,
the recommendation engine filters by area name (no lat/lon needed). This strategy
returns mode=AREA without attempting geocoding, keeping it fast and offline.

Examples:
    "Quận 3"         → area="quan 3", mode=AREA
    "ở Phú Nhuận"    → area="phu nhuan", mode=AREA
    "Đà Nẵng"        → area="da nang", mode=AREA
"""
from __future__ import annotations

from ...location_gazetteer import canonicalize_area_name
from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy


class DirectAreaStrategy(LocationStrategy):
    order = 40
    name = "direct_area"

    def can_handle(self, context: LocationContext) -> bool:
        return context.input_kind == "area" and bool(context.area_hint)

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        area_raw = context.area_hint
        # canonical_area: stable normalized key (already no-accent from classifier)
        # display_label:  human-readable Vietnamese form from gazetteer
        display = canonicalize_area_name(area_raw) or area_raw
        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.AREA,
            raw_phrase=context.location_phrase or context.raw_text,
            canonical_area=area_raw,
            display_label=display,
            # No lat/lon — recommendation engine uses area name for filtering
            latitude=None,
            longitude=None,
            radius_km=5.0,   # area-level search uses a moderate radius
            provider="area_match",
            cache_hit=False,
        )
