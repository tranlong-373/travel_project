"""
CurrentLocationStrategy — use browser GPS as the search anchor.

Handles:
  - amenity_only + user_location   → near_user (user gave amenities, no explicit area)
  - unknown + user_location         → near_user (no clear intent, GPS is best guess)

Does NOT fire for landmark/address/hotel inputs — those strategies provide
more specific location context and should take priority.
"""
from __future__ import annotations

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

# input_kinds where GPS is the correct/only location source
_GPS_ELIGIBLE_KINDS: frozenset[str] = frozenset({
    "amenity_only",
    "unknown",
})


class CurrentLocationStrategy(LocationStrategy):
    order = 10
    name = "current_location"

    def can_handle(self, context: LocationContext) -> bool:
        return (
            context.user_location is not None
            and context.input_kind in _GPS_ELIGIBLE_KINDS
        )

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        ul = context.user_location
        if ul is None:
            return None

        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.NEAR_USER,
            display_label="Vị trí hiện tại",
            latitude=ul.lat,
            longitude=ul.lon,
            radius_km=ul.radius_km or 10.0,
            provider="browser_gps",
            cache_hit=False,
            debug={"source": "user_location", "accuracy": ul.accuracy},
        )
