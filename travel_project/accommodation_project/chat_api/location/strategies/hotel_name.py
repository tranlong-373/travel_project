"""
HotelNameStrategy — resolve a named hotel via the Accommodation table.

Searches the Accommodation model by name (case-insensitive contains) BEFORE
falling through to geocoder. If a match is found, the hotel's stored coordinates
(if any) are used and mode is set to hotel_name so downstream code can show
a direct property card instead of a list.

If no Accommodation match is found, returns None to let later strategies
(FallbackGeocodeStrategy) attempt geocoding the hotel name.
"""
from __future__ import annotations

import logging
from typing import Any

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)


def _find_accommodation_by_name(name: str | None) -> dict[str, Any] | None:
    """
    Query Accommodation table for a hotel by name.
    Returns a plain dict with name/area/latitude/longitude or None.
    Wrapped for testability — patch this function in tests.
    """
    if not name:
        return None
    try:
        from accommodations.models import Accommodation

        acc = (
            Accommodation.objects
            .filter(name__icontains=name.strip())
            .values("id", "name", "area", "latitude", "longitude", "accommodation_type")
            .first()
        )
        return dict(acc) if acc else None
    except Exception as exc:
        logger.debug("hotel_name: DB lookup failed for %r: %s", name, exc)
        return None


class HotelNameStrategy(LocationStrategy):
    order = 30
    name = "hotel_name"

    def can_handle(self, context: LocationContext) -> bool:
        return context.input_kind == "hotel_name" and bool(context.hotel_name)

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        try:
            acc = _find_accommodation_by_name(context.hotel_name)
        except Exception as exc:
            logger.debug("hotel_name: resolve error: %s", exc)
            acc = None

        if acc is None:
            # No DB match — return UNRESOLVED hotel_name so downstream can show
            # a name-only card. Do NOT fall to geocoder or AMBIGUOUS.
            return ResolvedLocation(
                status=LocationStatus.UNRESOLVED,
                mode=LocationMode.HOTEL_NAME,
                raw_phrase=context.hotel_name or context.raw_text,
                anchor_name=context.hotel_name,
                anchor_kind="hotel",
                provider="hotel_name_only",
                cache_hit=False,
                debug={"source": "hotel_name_no_db_match", "hotel_name": context.hotel_name},
            )

        lat = acc.get("latitude")
        lon = acc.get("longitude")

        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.HOTEL_NAME,
            canonical_area=acc.get("area"),
            display_label=acc.get("name"),
            anchor_name=acc.get("name"),
            anchor_kind="hotel",
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            radius_km=1.0,
            provider="accommodation_db",
            cache_hit=True,
            debug={"accommodation_id": acc.get("id"), "accommodation_type": acc.get("accommodation_type")},
        )
