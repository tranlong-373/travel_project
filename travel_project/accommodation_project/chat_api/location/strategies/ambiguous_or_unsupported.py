"""
AmbiguousOrUnsupportedStrategy — final fallback for unresolvable inputs.

Fires when all other strategies have passed (returned None). Returns a
terminal ResolvedLocation with status UNRESOLVED or AMBIGUOUS — never None,
so the resolver always produces a result.

Routing:
  amenity_only (no GPS)   → UNRESOLVED + needs_area_clarification flag
  unknown / greeting      → UNRESOLVED
  everything else         → AMBIGUOUS (had location signal but couldn't resolve)
"""
from __future__ import annotations

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

_UNRESOLVED_KINDS: frozenset[str] = frozenset({
    "unknown",
    "greeting",
    "amenity_only",
})


class AmbiguousOrUnsupportedStrategy(LocationStrategy):
    order = 100
    name = "ambiguous_or_unsupported"

    def can_handle(self, context: LocationContext) -> bool:
        return True  # always fires as the final sentinel

    def resolve(self, context: LocationContext) -> ResolvedLocation:
        kind = context.input_kind

        # amenity_only without GPS: return UNRESOLVED so pipeline can ask for area
        if kind == "amenity_only":
            return ResolvedLocation(
                status=LocationStatus.UNRESOLVED,
                mode=LocationMode.UNKNOWN,
                raw_phrase=context.raw_text,
                debug={
                    "reason": "amenity_only_no_location",
                    "needs_area_clarification": True,
                    "amenity_terms": context.amenity_terms,
                },
            )

        # Pure input with no location semantics
        if kind in _UNRESOLVED_KINDS:
            return ResolvedLocation(
                status=LocationStatus.UNRESOLVED,
                mode=LocationMode.UNKNOWN,
                raw_phrase=context.raw_text,
                debug={"reason": f"no_location_signal_for_kind_{kind}"},
            )

        # landmark_or_poi / specific_address: keep status UNRESOLVED with a
        # near_anchor mode and the original phrase so filter_tree can retry
        # the geocoder (its `pending_phrase` path resolves real POIs that the
        # v2 fallback couldn't hit, e.g. when Nominatim is unreachable but
        # the test patches `chat_api.filter_tree.resolve_place_reference`).
        if kind in {"landmark_or_poi", "specific_address"}:
            phrase = context.location_phrase_raw or context.location_phrase or context.raw_text
            return ResolvedLocation(
                status=LocationStatus.UNRESOLVED,
                mode=LocationMode.NEAR_ANCHOR,
                raw_phrase=phrase,
                anchor_name=phrase,
                anchor_kind="unresolved",
                provider="pending_geocode",
                cache_hit=False,
                debug={
                    "reason": "fallback_geocode_miss_keep_pending",
                    "input_kind": kind,
                    "location_phrase": phrase,
                },
            )

        # Had location signal (landmark/address/mixed) but no strategy resolved it
        return ResolvedLocation(
            status=LocationStatus.AMBIGUOUS,
            mode=LocationMode.AMBIGUOUS,
            raw_phrase=context.location_phrase or context.raw_text,
            debug={
                "reason": "all_strategies_exhausted",
                "input_kind": kind,
                "location_phrase": context.location_phrase,
            },
        )
