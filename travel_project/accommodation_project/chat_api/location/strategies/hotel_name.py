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
    Look up an Accommodation by name. First tries a literal ``icontains`` match
    (fast path for clean names like "Hotel Phương Anh"), then falls back to the
    fuzzy candidate matcher (which handles "ACB", "Mường Thanh", "caravelle",
    typos, partial names, …).

    Returns a plain dict with name/area/latitude/longitude or None.
    """
    if not name:
        return None
    cleaned = name.strip()
    if not cleaned:
        return None

    try:
        from accommodations.models import Accommodation

        # 1. Try exact substring (fastest, no fuzzy overhead)
        acc = (
            Accommodation.objects
            .filter(name__icontains=cleaned)
            .values("id", "name", "area", "latitude", "longitude", "accommodation_type")
            .first()
        )
        if acc:
            return dict(acc)

        # 2. Fall back to fuzzy candidate matching (handles ACB-like cases)
        from ...input_classifier import _fuzzy_hotel_candidates
        from ...normalizers import normalize_key

        norm = normalize_key(cleaned)
        candidates = _fuzzy_hotel_candidates(norm, allow_no_keyword=True)
        if not candidates:
            return None

        top = candidates[0]
        # Load full details (incl. latitude/longitude) for the picked candidate
        full = (
            Accommodation.objects
            .filter(pk=top["accommodation_id"])
            .values("id", "name", "area", "latitude", "longitude", "accommodation_type")
            .first()
        )
        if full:
            return dict(full)
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
            return None  # no DB match — let later strategies (AmbiguousOrUnsupported) handle it

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
