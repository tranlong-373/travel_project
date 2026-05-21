"""
Adapter: SearchIntent → legacy parse_result dict.

Used for backward compatibility when existing code (recommendation_bridge,
views, tests) still expects a dict with the old key shape.
Phase 2 will progressively replace callers with direct SearchIntent usage.
"""
from __future__ import annotations

from typing import Any

from ..nlu.dto import SearchIntent


def to_parse_result(intent: SearchIntent) -> dict[str, Any]:
    """
    Convert a SearchIntent back to the legacy parse_result dict shape.
    Round-trip guarantee: from_parse_result(to_parse_result(intent)) should
    reproduce the same SearchIntent (modulo fields not carried in parse_result).
    """
    loc = intent.location

    slots: dict[str, Any] = {
        "area": intent.area,
        "budget": intent.budget,
        "budget_min": intent.budget_min,
        "budget_max": intent.budget_max,
        "guest_count": intent.guest_count,
        "trip_days": intent.trip_days,
        "accommodation_types": intent.accommodation_types,
        "preferred_type": intent.accommodation_types[0] if intent.accommodation_types else None,
        "accommodation_type": intent.accommodation_types[0] if intent.accommodation_types else None,
        "required_amenities": intent.required_amenities,
        "priorities": intent.priorities,
        "special_requirements": intent.special_requirements,
        "rating": intent.rating_min,
        "location_phrase": loc.raw_phrase,
        "location_mode": loc.mode.value,
        "hotel_name": intent.hotel_name,
    }

    if intent.user_location:
        slots["user_location"] = {
            "lat": intent.user_location.lat,
            "lon": intent.user_location.lon,
            "accuracy": intent.user_location.accuracy,
            "radius_km": intent.user_location.radius_km,
        }

    filter_tree_location: dict[str, Any] = {
        "mode": loc.mode.value,
        "canonical_area": loc.canonical_area,
        "anchor_lat": loc.latitude,
        "anchor_lon": loc.longitude,
        "anchor_name": loc.anchor_name,
        "anchor_kind": loc.anchor_kind,
        "search_radius_km": loc.radius_km,
        "nearby_poi_key": loc.nearby_poi_key,
        "nearby_place": loc.nearby_poi_label,
        "location_display_label": loc.display_label,
    }

    return {
        "conversation_intent": intent.conversation_intent,
        "intent": intent.conversation_intent,
        "slots": slots,
        "location_mode": loc.mode.value,
        "location_status": loc.status.value,
        "canonical_area": loc.canonical_area,
        "location_display_label": loc.display_label,
        "anchor_name": loc.anchor_name,
        "anchor_kind": loc.anchor_kind,
        "anchor_lat": loc.latitude,
        "anchor_lon": loc.longitude,
        "search_radius_km": loc.radius_km,
        "location_confidence": intent.confidence,
        "used_default_slots": intent.used_default_slots,
        "selected_place": intent.selected_place,
        "filter_tree": {
            "location": filter_tree_location,
            "filters": [],
            "usable_filter_count": 0,
            "available_slots": [],
            "missing_slots": [],
        },
    }
