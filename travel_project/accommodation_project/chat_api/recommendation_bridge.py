from __future__ import annotations

from typing import Any

from django.urls import reverse

from preferences.models import UserPreference


DOWNSTREAM_TYPES = {"hotel", "homestay", "hostel", "apartment"}
BLOCKED_INTENTS = {"off_topic", "unknown", "greeting", "thanks", "help", "goodbye"}
BLOCKED_LOCATION_STATUSES = {"conflict", "multiple_choice", "unsupported", "unresolved", "ambiguous"}
DEFAULT_NEARBY_RADIUS_KM = 10.0


def create_preference_from_parse(parse_result: dict[str, Any]) -> dict[str, Any]:
    user_location = _read_user_location(parse_result)
    has_user_location = bool(user_location)

    if not parse_result.get("can_show_recommendations", parse_result.get("ready_for_recommendation")):
        raise ValueError("Parse result is not ready for recommendation.")
    if parse_result.get("recommendation_level") == "none" and not has_user_location:
        raise ValueError("Parse result has no recommendation level.")
    if (
        parse_result.get("conversation_intent") in BLOCKED_INTENTS
        or parse_result.get("intent") in BLOCKED_INTENTS
    ) and not has_user_location:
        raise ValueError("Conversation intent is not eligible for recommendation.")

    if parse_result.get("location_status") in BLOCKED_LOCATION_STATUSES and not has_user_location:
        raise ValueError("Location is not eligible for recommendation.")

    slots = parse_result.get("slots") or {}
    area = slots.get("area") or parse_result.get("canonical_area")
    if has_user_location:
        area = "Vi tri hien tai"
    if not area:
        raise ValueError("Parse result has no supported area.")

    preferred_type = slots.get("preferred_type") or None
    if preferred_type not in DOWNSTREAM_TYPES:
        preferred_type = None

    used_default_slots = dict(parse_result.get("used_default_slots") or {})
    budget = slots.get("budget") or slots.get("budget_max")
    if budget is None:
        budget = 0
        used_default_slots["budget"] = {
            "value": 0,
            "reason": "user_missing_budget_no_budget_filter",
        }

    guest_count = slots.get("guest_count")
    if guest_count is None:
        guest_count = 1
        used_default_slots["guest_count"] = {
            "value": 1,
            "reason": "user_missing_guest_count_safe_minimum",
        }

    preference_kwargs = {
        "area": area,
        "budget": budget,
        "guest_count": guest_count,
        "preferred_type": preferred_type,
        "required_amenities": slots.get("required_amenities") or [],
    }
    if has_user_location:
        preference_kwargs.update(
            {
                "user_latitude": user_location["lat"],
                "user_longitude": user_location["lon"],
                "search_radius_km": user_location.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM,
            }
        )

    preference = UserPreference.objects.create(**preference_kwargs)

    return {
        "pref_id": preference.id,
        "recommendation_url": reverse("recommendation_result", kwargs={"pref_id": preference.id}),
        "used_default_slots": used_default_slots,
        "user_location_used": has_user_location,
    }


def _read_user_location(parse_result: dict[str, Any]) -> dict[str, float] | None:
    raw_location = parse_result.get("user_location")
    if not isinstance(raw_location, dict):
        raw_location = (parse_result.get("slots") or {}).get("user_location")
    if not isinstance(raw_location, dict):
        return None

    try:
        lat = float(raw_location.get("lat"))
        lon = float(raw_location.get("lon"))
    except (TypeError, ValueError):
        return None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    radius_km = raw_location.get("radius_km") or raw_location.get("radius")
    try:
        radius_km = float(radius_km) if radius_km is not None else DEFAULT_NEARBY_RADIUS_KM
    except (TypeError, ValueError):
        radius_km = DEFAULT_NEARBY_RADIUS_KM

    radius_km = min(max(radius_km, 1.0), 50.0)
    return {"lat": lat, "lon": lon, "radius_km": radius_km}
