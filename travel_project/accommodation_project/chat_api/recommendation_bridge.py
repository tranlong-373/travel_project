from __future__ import annotations

from typing import Any

from django.urls import reverse

from preferences.models import UserPreference


DOWNSTREAM_TYPES = {"hotel", "homestay", "hostel", "apartment"}


def create_preference_from_parse(parse_result: dict[str, Any]) -> dict[str, Any]:
    if not parse_result.get("ready_for_recommendation"):
        raise ValueError("Parse result is not ready for recommendation.")

    slots = parse_result.get("slots") or {}
    preferred_type = slots.get("preferred_type") or None
    if preferred_type not in DOWNSTREAM_TYPES:
        preferred_type = None

    preference = UserPreference.objects.create(
        area=slots["area"],
        budget=slots.get("budget") or slots["budget_max"],
        guest_count=slots["guest_count"],
        preferred_type=preferred_type,
        required_amenities=slots.get("required_amenities") or [],
    )

    return {
        "pref_id": preference.id,
        "recommendation_url": reverse("recommendation_result", kwargs={"pref_id": preference.id}),
    }
