from __future__ import annotations

from typing import Any

from django.urls import reverse

from preferences.models import UserPreference


DOWNSTREAM_TYPES = {"hotel", "homestay", "hostel", "apartment"}
BLOCKED_INTENTS = {"off_topic", "unknown", "greeting", "thanks", "help", "goodbye"}
BLOCKED_LOCATION_STATUSES = {"conflict", "multiple_choice", "unsupported", "unresolved", "ambiguous"}


def create_preference_from_parse(parse_result: dict[str, Any]) -> dict[str, Any]:
    if not parse_result.get("can_show_recommendations", parse_result.get("ready_for_recommendation")):
        raise ValueError("Parse result is not ready for recommendation.")
    if parse_result.get("recommendation_level") == "none":
        raise ValueError("Parse result has no recommendation level.")
    if parse_result.get("conversation_intent") in BLOCKED_INTENTS or parse_result.get("intent") in BLOCKED_INTENTS:
        raise ValueError("Conversation intent is not eligible for recommendation.")
    if parse_result.get("location_status") in BLOCKED_LOCATION_STATUSES:
        raise ValueError("Location is not eligible for recommendation.")

    slots = parse_result.get("slots") or {}
    area = slots.get("area") or parse_result.get("canonical_area")
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

    preference = UserPreference.objects.create(
        area=area,
        budget=budget,
        guest_count=guest_count,
        preferred_type=preferred_type,
        required_amenities=slots.get("required_amenities") or [],
    )

    return {
        "pref_id": preference.id,
        "recommendation_url": reverse("recommendation_result", kwargs={"pref_id": preference.id}),
        "used_default_slots": used_default_slots,
    }
