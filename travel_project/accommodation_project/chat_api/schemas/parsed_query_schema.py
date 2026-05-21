from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "2.0"
INTENT_DEFAULT = "recommend_accommodation"

CORE_MISSING_KEYS = ("area", "budget", "guest_count", "trip_days")

DOWNSTREAM_TYPES = {"hotel", "homestay", "hostel", "apartment"}
ALLOWED_TYPES = DOWNSTREAM_TYPES | {"resort", "villa"}

ALLOWED_AMENITIES = {
    "wifi",
    "pool",
    "parking",
    "air_conditioner",
    "breakfast",
    "balcony",
    "bathtub",
    "kitchen",
    "washing_machine",
}

ALLOWED_PRIORITIES = {
    "near_center",
    "near_beach",
    "cheap",
    "quiet",
    "high_rating",
    "nice_view",
    "clean",
    "convenient",
}

ALLOWED_SPECIAL_REQUIREMENTS = {
    "baby_friendly",
    "elderly_friendly",
    "pet_friendly",
    "work_friendly",
    "family_friendly",
    "couple_friendly",
    "private",
    "safe_area",
}

DEFAULT_SLOTS: dict[str, Any] = {
    "area": None,
    "budget": None,
    "budget_min": None,
    "budget_max": None,
    "guest_count": None,
    "preferred_type": None,
    "accommodation_type": None,
    "accommodation_types": [],
    "required_amenities": [],
    "priorities": [],
    "special_requirements": [],
    "trip_days": None,
    "room_count": None,
    "rating": None,
    "check_in": None,
    "check_out": None,
    "location_phrase": None,
    "location_mode": "unknown",
}


def empty_slots() -> dict[str, Any]:
    return deepcopy(DEFAULT_SLOTS)
