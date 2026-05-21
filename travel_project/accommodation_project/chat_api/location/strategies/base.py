"""
Abstract base class for location resolution strategies.
Strategy chain pattern — each strategy either resolves or yields to the next.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...nlu.dto import ResolvedLocation
from ..context import LocationContext


class LocationStrategy(ABC):
    """
    Pluggable location resolution strategy.

    Subclasses MUST define:
        order : int  — execution priority (lower = runs earlier); set as class attribute.
        name  : str  — unique identifier for logging.
        can_handle(ctx) -> bool
        resolve(ctx)    -> ResolvedLocation | None

    Contract:
        - can_handle() must never raise.
        - resolve() must never raise — catch internally and return None on failure.
        - Return None to pass control to the next strategy.
        - Return a ResolvedLocation (status OK/GEOCODED/AMBIGUOUS) to stop the chain.

    Registered strategies:
        10  CurrentLocationStrategy       — browser GPS → near_user
        20  SelectedPlaceStrategy         — user picked from multiple_choice → near_anchor
        30  HotelNameStrategy             — Accommodation table search → hotel_name
        40  DirectAreaStrategy            — area-only query → area (no coords needed)
        50  NearAnchorFromPlaceReference  — PlaceReference cache hit → near_anchor
        60  FallbackGeocodeStrategy       — external geocoder → near_anchor
        70  PoiCentroidStrategy           — generic_poi_in_area → area centroid
       100  AmbiguousOrUnsupportedStrategy — final fallback
    """

    order: int = 999  # override in each subclass; lower = higher priority

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier used in debug output and logging."""
        ...

    @abstractmethod
    def can_handle(self, context: LocationContext) -> bool:
        """
        Quick pre-check. Return False to skip entirely.
        Must never raise.
        """
        ...

    @abstractmethod
    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        """
        Attempt resolution.
        - Return ResolvedLocation on success (status OK or GEOCODED).
        - Return None to pass to next strategy.
        - Must never raise externally.
        """
        ...
