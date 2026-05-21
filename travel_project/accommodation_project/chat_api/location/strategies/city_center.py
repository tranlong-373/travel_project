"""
CityCenterStrategy — handles "trung tâm thành phố" / "gần trung tâm Hà Nội" / "downtown".

Reuses v1's chat_api.city_center module so coordinates, aliases and the city
gazetteer stay in one place.  Fires when context.input_kind == "city_center"
(set by InputClassifierV2 when it detects a city-center phrase).
"""
from __future__ import annotations

import logging

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)


class CityCenterStrategy(LocationStrategy):
    # Run before DirectArea so "trung tâm" doesn't get treated as a plain area.
    order = 32
    name = "city_center"

    def can_handle(self, context: LocationContext) -> bool:
        return context.input_kind == "city_center"

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        try:
            from ...city_center import (
                city_hint_from_text,
                default_search_city,
                resolve_city_center,
            )
        except Exception as exc:
            logger.debug("city_center: v1 module unavailable: %s", exc)
            return None

        # Prefer an explicit city mentioned in the text; fall back to default.
        city = (
            context.area_hint
            or city_hint_from_text(context.raw_text)
            or default_search_city()
        )

        if not city:
            # No city resolved → ambiguous (needs clarification).
            return ResolvedLocation(
                status=LocationStatus.AMBIGUOUS,
                mode=LocationMode.CITY_CENTER,
                raw_phrase="trung tâm thành phố",
                display_label="trung tâm thành phố",
                anchor_kind="city_center",
                provider="semantic",
                cache_hit=False,
                debug={
                    "reason": "needs_city_for_city_center",
                    "needs_city_clarification": True,
                },
            )

        center = resolve_city_center(city)
        if not center:
            return None

        return ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.CITY_CENTER,
            raw_phrase="trung tâm thành phố",
            canonical_area=center.get("canonical_area"),
            display_label=center.get("location_display_label"),
            anchor_name=center.get("anchor_name"),
            anchor_kind="city_center",
            latitude=center.get("anchor_lat"),
            longitude=center.get("anchor_lon"),
            radius_km=float(center.get("anchor_radius_km") or 4.0),
            provider=center.get("provider") or "semantic",
            cache_hit=True,  # static gazetteer, never calls geocoder
            debug={"source": "v1_city_center", "city": city},
        )
