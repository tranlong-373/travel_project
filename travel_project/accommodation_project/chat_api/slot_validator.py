from __future__ import annotations

import re
from typing import Any

from .agent.schema_normalizer import extract_budget_bounds
from .extractors import (
    extract_guest_count,
    find_type_candidates,
    extract_preferred_type,
    extract_priorities,
    extract_required_amenities,
    extract_special_requirements,
    extract_trip_days,
    find_unsupported_type_candidates,
    has_type_choice_connector,
)
from .schema import ALLOWED_AMENITIES, ALLOWED_PRIORITIES, ALLOWED_SPECIAL_REQUIREMENTS, ALLOWED_TYPES, empty_slots
from .slot_pipeline import build_slot_parse_context
from .text_normalizer import normalize_user_text
from .validators import validate_and_normalize_slots


def extract_slots_from_text(
    text: str,
    *,
    canonical_area: str | None = None,
    slot_parse_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    slot_parse_context = slot_parse_context or build_slot_parse_context(text)
    budget_min, budget_max = extract_budget_bounds(search_text)
    accommodation_types = slot_parse_context.get("accommodation_types") or find_type_candidates(search_text)
    preferred_type = None if len(accommodation_types) > 1 and has_type_choice_connector(search_text) else (
        accommodation_types[0] if accommodation_types else extract_preferred_type(search_text)
    )
    check_in, check_out = _extract_date_bounds(search_text)
    search_radius_km = slot_parse_context.get("search_radius_km") or _extract_search_radius_km(search_text)

    slots = empty_slots()
    slots.update(
        {
            "area": canonical_area,
            "budget": budget_max,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "guest_count": extract_guest_count(search_text),
            "preferred_type": preferred_type,
            "accommodation_type": preferred_type,
            "accommodation_types": accommodation_types,
            "type_choice_multiple": bool(len(accommodation_types) > 1 and has_type_choice_connector(search_text)),
            "required_amenities": slot_parse_context.get("required_amenities") or extract_required_amenities(search_text),
            "priorities": extract_priorities(search_text),
            "special_requirements": extract_special_requirements(search_text),
            "trip_days": extract_trip_days(search_text),
            "room_count": _extract_room_count(search_text),
            "rating": _extract_rating(search_text),
            "search_radius_km": search_radius_km,
            "check_in": check_in,
            "check_out": check_out,
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
        "accommodation_type",
        "trip_days",
        "room_count",
        "rating",
        "search_radius_km",
        "check_in",
        "check_out",
        "location_phrase",
        "location_mode",
        "raw_preferred_type",
        "unsupported_preferred_type",
    ]:
        value = slots_new.get(key)
        if key == "location_mode" and value == "unknown" and merged.get("location_mode") not in {None, "unknown"}:
            continue
        if value is not None:
            merged[key] = value

    for key in ["accommodation_types", "required_amenities", "priorities", "special_requirements"]:
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

    accommodation_types = _filter_allowed(slots.get("accommodation_types"), ALLOWED_TYPES)
    type_choice_multiple = bool(slots_partial.get("type_choice_multiple"))
    preferred_type = slots.get("preferred_type")
    if not preferred_type and accommodation_types and not type_choice_multiple:
        preferred_type = accommodation_types[0]
    accommodation_type = slots.get("accommodation_type") or preferred_type
    if preferred_type not in ALLOWED_TYPES:
        preferred_type = None
    if accommodation_type not in ALLOWED_TYPES:
        accommodation_type = preferred_type
    if type_choice_multiple:
        preferred_type = None
        accommodation_type = None
    if not accommodation_types:
        accommodation_types = [value for value in [preferred_type, accommodation_type] if value in ALLOWED_TYPES]
        accommodation_types = list(dict.fromkeys(accommodation_types))
    slots["preferred_type"] = preferred_type
    slots["accommodation_type"] = accommodation_type
    slots["accommodation_types"] = accommodation_types

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

    room_count = _as_int(slots_partial.get("room_count") or slots.get("room_count"))
    slots["room_count"] = room_count if room_count is not None and 1 <= room_count <= 20 else None

    rating = _as_float(slots_partial.get("rating") or slots.get("rating"))
    slots["rating"] = rating if rating is not None and 0 < rating <= 5 else None

    search_radius_km = _as_float(slots_partial.get("search_radius_km") or slots.get("search_radius_km"))
    slots["search_radius_km"] = search_radius_km if search_radius_km is not None and 0.1 <= search_radius_km <= 50 else None

    for key in ("check_in", "check_out", "location_phrase"):
        value = slots_partial.get(key) or slots.get(key)
        slots[key] = str(value).strip() if value else None
    location_mode = slots_partial.get("location_mode") or slots.get("location_mode") or "unknown"
    slots["location_mode"] = str(location_mode).strip() or "unknown"

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


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
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


def _extract_room_count(text: str | None) -> int | None:
    normalized = normalize_user_text(text or "")
    search_text = " ".join(
        value
        for value in [
            normalized["raw_text"],
            normalized["normalized_text"],
            normalized["no_accent_text"],
        ]
        if value
    )
    match = re.search(
        r"(?<!\d)(\d{1,2})\s*(?:phòng|phong|rooms?|room)\b",
        search_text,
        re.IGNORECASE,
    )
    return _as_int(match.group(1)) if match else None


def _extract_rating(text: str | None) -> float | None:
    normalized = normalize_user_text(text or "")
    norm = normalized["no_accent_text"]
    direct_match = re.search(r"(?<!\d)([1-5](?:[.,]\d)?)\s*(?:sao|star|diem|rating)\b", norm, re.IGNORECASE)
    if direct_match:
        return _as_float(direct_match.group(1))
    match = re.search(
        r"(?:rating|danh gia|diem|sao|star)\s*(?:tu|tren|>=|ít nhất|it nhat)?\s*([1-5](?:[.,]\d)?)|(?:tu|tren|>=|ít nhất|it nhat)\s*([1-5](?:[.,]\d)?)\s*(?:sao|star|diem)",
        norm,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _as_float(match.group(1) or match.group(2))


def _extract_search_radius_km(text: str | None) -> float | None:
    normalized = normalize_user_text(text or "")
    norm = normalized["no_accent_text"]
    unit_pattern = r"km|kilomet|kilometer|kilometre|kilometers|kilometres|cay"
    patterns = (
        rf"\b(?:trong|ban\s+kinh|pham\s+vi)\s*(\d+(?:[.,]\d+)?)\s*(?:{unit_pattern})\b",
        rf"\b(\d+(?:[.,]\d+)?)\s*(?:{unit_pattern})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, norm, flags=re.IGNORECASE)
        if not match:
            continue
        radius = _as_float(match.group(1))
        if radius is not None and 0.1 <= radius <= 50:
            return round(radius, 2)
    return None


def _extract_date_bounds(text: str | None) -> tuple[str | None, str | None]:
    normalized = normalize_user_text(text or "")
    raw = normalized["raw_text"]
    date_pattern = r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{1,2}-\d{1,2})"
    check_in = None
    check_out = None

    in_match = re.search(
        rf"(?:check\s*in|nhận phòng|nhan phong|từ ngày|tu ngay)\s*{date_pattern}",
        raw,
        re.IGNORECASE,
    )
    if in_match:
        check_in = in_match.group(1)

    out_match = re.search(
        rf"(?:check\s*out|trả phòng|tra phong|đến ngày|den ngay)\s*{date_pattern}",
        raw,
        re.IGNORECASE,
    )
    if out_match:
        check_out = out_match.group(1)

    return check_in, check_out
