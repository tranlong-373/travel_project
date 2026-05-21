"""
LocationResolver v2 — runs registered strategies sorted by order.

Usage:
    resolver = LocationResolver.default()
    location = resolver.resolve(LocationContext(
        raw_text="gần Landmark 81",
        input_kind="landmark_or_poi",
        location_phrase="landmark 81",
    ))
"""
from __future__ import annotations

import logging

from ..nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from .context import LocationContext
from .strategies.base import LocationStrategy

logger = logging.getLogger(__name__)


class LocationResolver:
    """
    Executes strategies sorted by `order` (lowest first).
    Returns the first non-None result, or an UNRESOLVED sentinel.
    Thread-safe: strategies are never mutated after construction.
    """

    def __init__(self, strategies: list[LocationStrategy] | None = None) -> None:
        self._strategies: list[LocationStrategy] = list(strategies or [])

    # ── Configuration ────────────────────────────────────────────────────────

    def register(self, strategy: LocationStrategy) -> None:
        self._strategies.append(strategy)

    def register_many(self, strategies: list[LocationStrategy]) -> None:
        self._strategies.extend(strategies)

    @property
    def strategy_names(self) -> list[str]:
        return [s.name for s in self._sorted_strategies]

    @property
    def _sorted_strategies(self) -> list[LocationStrategy]:
        return sorted(self._strategies, key=lambda s: s.order)

    # ── Resolution ───────────────────────────────────────────────────────────

    def resolve(self, context: LocationContext) -> ResolvedLocation:
        """
        Run strategies in order. Return first successful resolution.
        Always returns a ResolvedLocation — never raises.
        """
        attempted: list[str] = []

        for strategy in self._sorted_strategies:
            if not strategy.can_handle(context):
                continue

            attempted.append(strategy.name)
            try:
                result = strategy.resolve(context)
            except Exception as exc:
                logger.debug("resolver: strategy %s raised: %s", strategy.name, exc)
                result = None

            if result is not None:
                if context.debug:
                    result.debug.setdefault("resolved_by", strategy.name)
                    result.debug.setdefault("attempted", attempted)
                return result

        return ResolvedLocation(
            status=LocationStatus.UNRESOLVED,
            mode=LocationMode.UNKNOWN,
            raw_phrase=context.raw_text,
            debug={"attempted": attempted} if context.debug else {},
        )

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "LocationResolver":
        """
        Build a resolver with all production strategies registered in order.
        Lazy imports ensure Django isn't needed at module load time.
        """
        from .strategies.current_location import CurrentLocationStrategy
        from .strategies.selected_place import SelectedPlaceStrategy
        from .strategies.hotel_name import HotelNameStrategy
        from .strategies.city_center import CityCenterStrategy
        from .strategies.multi_choice_conflict import MultiChoiceConflictStrategy
        from .strategies.direct_area import DirectAreaStrategy
        from .strategies.near_anchor import NearAnchorFromPlaceReferenceStrategy
        from .strategies.landmark_static_json import LandmarkStaticJsonStrategy
        from .strategies.fallback_geocode import FallbackGeocodeStrategy
        from .strategies.mixed_search_area import MixedSearchAreaFallbackStrategy
        from .strategies.poi_centroid import PoiCentroidStrategy
        from .strategies.ambiguous_or_unsupported import AmbiguousOrUnsupportedStrategy

        return cls([
            CurrentLocationStrategy(),
            SelectedPlaceStrategy(),
            HotelNameStrategy(),
            CityCenterStrategy(),
            MultiChoiceConflictStrategy(),
            DirectAreaStrategy(),
            NearAnchorFromPlaceReferenceStrategy(),
            LandmarkStaticJsonStrategy(),
            FallbackGeocodeStrategy(),
            MixedSearchAreaFallbackStrategy(),
            PoiCentroidStrategy(),
            AmbiguousOrUnsupportedStrategy(),
        ])
