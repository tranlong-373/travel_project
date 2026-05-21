"""
SelectedPlaceStrategy — user explicitly chose a place from a multiple_choice list.

When the user resolves an ambiguous location by picking one of the offered options,
the selected canonical name is stored in context.selected_place. This strategy
looks it up in PlaceReference and returns a near_anchor result.
"""
from __future__ import annotations

import logging
from typing import Any

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)


def _lookup_place_reference(phrase: str | None) -> dict[str, Any] | None:
    """PlaceReference DB lookup — wrapped for testability (patch this function)."""
    if not phrase:
        return None
    try:
        from ...services.place_reference import find_place_reference
        return find_place_reference(phrase)
    except Exception as exc:
        logger.debug("selected_place: place_reference lookup failed: %s", exc)
        return None


def _ref_to_resolved(ref: dict[str, Any], *, cache_hit: bool = True) -> ResolvedLocation:
    lat = ref.get("latitude") or ref.get("lat")
    lon = ref.get("longitude") or ref.get("lon")
    return ResolvedLocation(
        status=LocationStatus.OK,
        mode=LocationMode.NEAR_ANCHOR,
        canonical_area=ref.get("canonical_name") or ref.get("display_name"),
        display_label=ref.get("display_name") or ref.get("canonical_name"),
        anchor_name=ref.get("canonical_name") or ref.get("name"),
        anchor_kind=ref.get("kind") or ref.get("place_type"),
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        radius_km=float(ref.get("default_radius_km") or 5.0),
        provider=ref.get("provider") or "cache",
        cache_hit=cache_hit,
    )


class SelectedPlaceStrategy(LocationStrategy):
    order = 20
    name = "selected_place"

    def can_handle(self, context: LocationContext) -> bool:
        return bool(context.selected_place)

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        ref = _lookup_place_reference(context.selected_place)
        if ref is None:
            return None
        return _ref_to_resolved(ref, cache_hit=True)
