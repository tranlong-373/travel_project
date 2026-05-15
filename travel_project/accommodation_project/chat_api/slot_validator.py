from __future__ import annotations

from typing import Any

from .agent.schema_normalizer import extract_budget_bounds
from .extractors import (
    extract_guest_count,
    extract_preferred_type,
    extract_priorities,
    extract_required_amenities,
    extract_special_requirements,
    extract_trip_days,
    find_unsupported_type_candidates,
)
from .schema import ALLOWED_AMENITIES, ALLOWED_PRIORITIES, ALLOWED_SPECIAL_REQUIREMENTS, ALLOWED_TYPES, empty_slots
from .text_normalizer import normalize_user_text
from .validators import validate_and_normalize_slots


def extract_slots_from_text(text: str, *, canonical_area: str | None = None) -> dict[str, Any]:
    normalized = normalize_user_text(text)
    search_text = " ".join(
        value
        for value in [
            normalized["raw_text"],
            normalized["normalized_text"],
            normalized["no_accent_text"],
        ]
        if value
    )
    budget_min, budget_max = extract_budget_bounds(search_text)

    slots = empty_slots()
    slots.update(
        {
            "area": canonical_area,
            "budget": budget_max,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "guest_count": extract_guest_count(search_text),
            "preferred_type": extract_preferred_type(search_text),
            "required_amenities": extract_required_amenities(search_text),
            "priorities": extract_priorities(search_text),
            "special_requirements": extract_special_requirements(search_text),
            "trip_days": extract_trip_days(search_text),
        }
    )

    unsupported_types = find_unsupported_type_candidates(search_text)
    if unsupported_types:
        slots["raw_preferred_type"] = unsupported_types[0]
        slots["unsupported_preferred_type"] = unsupported_types[0]

    return slots


def merge_slot_context(
    slots_new: dict[str, Any],
    context_slots: dict[str, Any] | None,
    *,
    replace_area: bool = False,
) -> dict[str, Any]:
    if not context_slots:
        return slots_new

    merged = dict(context_slots)
    if replace_area:
        merged.pop("area", None)
        merged.pop("canonical_area", None)

    for key in [
        "area",
        "canonical_area",
        "budget",
        "budget_min",
        "budget_max",
        "guest_count",
        "preferred_type",
        "trip_days",
        "raw_preferred_type",
        "unsupported_preferred_type",
    ]:
        value = slots_new.get(key)
        if value is not None:
            merged[key] = value

    for key in ["required_amenities", "priorities", "special_requirements"]:
        base = merged.get(key) or []
        add = slots_new.get(key) or []
        merged[key] = list(dict.fromkeys([*base, *add]))

    return merged


def validate_slots(slots_partial: dict[str, Any]) -> dict[str, Any]:
    slots = validate_and_normalize_slots(slots_partial)

    budget_min = _reasonable_budget(slots_partial.get("budget_min"))
    budget_max = _reasonable_budget(slots_partial.get("budget_max") or slots.get("budget"))
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        budget_min, budget_max = budget_max, budget_min
    slots["budget_min"] = budget_min
    slots["budget_max"] = budget_max
    slots["budget"] = budget_max

    guest_count = _as_int(slots.get("guest_count"))
    slots["guest_count"] = guest_count if guest_count is not None and 1 <= guest_count <= 30 else None

    trip_days = _as_int(slots.get("trip_days"))
    slots["trip_days"] = trip_days if trip_days is not None and 1 <= trip_days <= 365 else None

    preferred_type = slots.get("preferred_type")
    if preferred_type not in ALLOWED_TYPES:
        preferred_type = None
    slots["preferred_type"] = preferred_type

    slots["required_amenities"] = _filter_allowed(slots.get("required_amenities"), ALLOWED_AMENITIES)
    slots["priorities"] = _filter_allowed(slots.get("priorities"), ALLOWED_PRIORITIES)
    slots["special_requirements"] = _filter_allowed(
        slots.get("special_requirements"),
        ALLOWED_SPECIAL_REQUIREMENTS,
    )

    if slots_partial.get("raw_preferred_type"):
        slots["raw_preferred_type"] = str(slots_partial["raw_preferred_type"]).strip().lower()
    if slots_partial.get("unsupported_preferred_type"):
        slots["unsupported_preferred_type"] = str(slots_partial["unsupported_preferred_type"]).strip().lower()

    return slots


def core_missing_slots(slots: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not slots.get("area"):
        missing.append("area")
    if not (slots.get("budget") or slots.get("budget_max")):
        missing.append("budget")
    if not slots.get("guest_count"):
        missing.append("guest_count")
    if not slots.get("trip_days"):
        missing.append("trip_days")
    return missing


def _reasonable_budget(value: Any) -> int | None:
    amount = _as_int(value)
    if amount is None:
        return None
    if 50_000 <= amount <= 200_000_000:
        return amount
    return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace(".", "")
        if cleaned.isdigit():
            return int(cleaned)
    return None


def _filter_allowed(values: Any, allowed: set[str]) -> list[str]:
    if not isinstance(values, list):
        return []
    filtered: list[str] = []
    for value in values:
        key = str(value).strip().lower()
        if key in allowed and key not in filtered:
            filtered.append(key)
    return filtered
