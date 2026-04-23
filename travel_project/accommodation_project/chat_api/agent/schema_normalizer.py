from __future__ import annotations

import os
import re
from typing import Any

from ..extractors import (
    extract_guest_count,
    extract_priorities,
    find_type_candidates,
    has_type_choice_connector,
    extract_required_amenities,
    extract_special_requirements,
    extract_trip_days,
)
from ..normalizers import normalize_key
from ..questions import build_suggested_questions
from ..validators import AREA_ALIAS_FLAT
from ..schemas.parsed_query_schema import (
    ALLOWED_AMENITIES,
    ALLOWED_PRIORITIES,
    ALLOWED_SPECIAL_REQUIREMENTS,
    ALLOWED_TYPES,
    CORE_MISSING_KEYS,
    INTENT_DEFAULT,
    SCHEMA_VERSION,
    empty_slots,
)

MONEY_UNITS = r"k|nghin|ngan|thousand|tr|trieu|m|cu|million|mil|mio"

AREA_ALIASES = {
    normalize_key(alias): canonical
    for alias, canonical in {
        **AREA_ALIAS_FLAT,
        "da lat": "đà lạt",
        "đà lạt": "đà lạt",
        "vung tau": "vũng tàu",
        "vũng tàu": "vũng tàu",
        "phu quoc": "phú quốc",
        "phú quốc": "phú quốc",
        "da nang": "đà nẵng",
        "đà nẵng": "đà nẵng",
        "nha trang": "nha trang",
        "sapa": "sapa",
        "sa pa": "sapa",
        "can tho": "cần thơ",
        "cần thơ": "cần thơ",
        "mui ne": "mũi né",
        "mũi né": "mũi né",
    }.items()
}

TYPE_ALIASES = {
    "khach san": "hotel",
    "khách sạn": "hotel",
    "hotel": "hotel",
    "ks": "hotel",
    "homestay": "homestay",
    "home stay": "homestay",
    "hostel": "hostel",
    "nha nghi": "hostel",
    "nhà nghỉ": "hostel",
    "dorm": "hostel",
    "can ho": "apartment",
    "căn hộ": "apartment",
    "apartment": "apartment",
    "chung cu": "apartment",
    "resort": "resort",
    "khu nghi duong": "resort",
    "khu nghỉ dưỡng": "resort",
    "villa": "villa",
    "biet thu": "villa",
    "biệt thự": "villa",
}

AMENITY_ALIASES = {
    "wifi": "wifi",
    "wi fi": "wifi",
    "wi-fi": "wifi",
    "internet": "wifi",
    "mang": "wifi",
    "mạng": "wifi",
    "wifi manh": "wifi",
    "wifi mạnh": "wifi",
    "ho boi": "pool",
    "hồ bơi": "pool",
    "be boi": "pool",
    "bể bơi": "pool",
    "pool": "pool",
    "bai do xe": "parking",
    "bãi đỗ xe": "parking",
    "cho dau xe": "parking",
    "chỗ đậu xe": "parking",
    "parking": "parking",
    "may lanh": "air_conditioner",
    "máy lạnh": "air_conditioner",
    "dieu hoa": "air_conditioner",
    "điều hòa": "air_conditioner",
    "ac": "air_conditioner",
    "an sang": "breakfast",
    "ăn sáng": "breakfast",
    "breakfast": "breakfast",
    "ban cong": "balcony",
    "ban công": "balcony",
    "bon tam": "bathtub",
    "bồn tắm": "bathtub",
    "bep": "kitchen",
    "bếp": "kitchen",
    "kitchen": "kitchen",
    "may giat": "washing_machine",
    "máy giặt": "washing_machine",
}

PRIORITY_ALIASES = {
    "gan trung tam": "near_center",
    "gần trung tâm": "near_center",
    "near center": "near_center",
    "thuan tien": "convenient",
    "thuận tiện": "convenient",
    "yen tinh": "quiet",
    "yên tĩnh": "quiet",
    "quiet": "quiet",
    "gan bien": "near_beach",
    "gần biển": "near_beach",
    "near beach": "near_beach",
    "view dep": "nice_view",
    "view đẹp": "nice_view",
    "nice view": "nice_view",
    "sach se": "clean",
    "sạch sẽ": "clean",
    "clean": "clean",
    "re": "cheap",
    "rẻ": "cheap",
    "gia re": "cheap",
    "giá rẻ": "cheap",
    "rating cao": "high_rating",
    "danh gia cao": "high_rating",
    "đánh giá cao": "high_rating",
}

SPECIAL_ALIASES = {
    "cong tac": "work_friendly",
    "công tác": "work_friendly",
    "lam viec": "work_friendly",
    "làm việc": "work_friendly",
    "ban lam viec": "work_friendly",
    "bàn làm việc": "work_friendly",
    "remote work": "work_friendly",
    "workation": "work_friendly",
    "gia dinh": "family_friendly",
    "gia đình": "family_friendly",
    "family": "family_friendly",
    "couple": "couple_friendly",
    "cap doi": "couple_friendly",
    "cặp đôi": "couple_friendly",
    "nguoi yeu": "couple_friendly",
    "người yêu": "couple_friendly",
    "thu cung": "pet_friendly",
    "thú cưng": "pet_friendly",
    "pet": "pet_friendly",
    "nguoi lon tuoi": "elderly_friendly",
    "người lớn tuổi": "elderly_friendly",
    "em be": "baby_friendly",
    "em bé": "baby_friendly",
    "rieng tu": "private",
    "riêng tư": "private",
    "an toan": "safe_area",
    "an toàn": "safe_area",
}


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 else None
    if isinstance(value, str):
        bounds = extract_budget_bounds(value)
        if bounds[1]:
            return bounds[1]
        digits = re.sub(r"[^\d]", "", value)
        if digits:
            parsed = int(digits)
            return parsed if parsed > 0 else None
    return None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    return []


def _money_to_vnd(num_str: str, unit: str | None) -> int:
    number = float(num_str.replace(",", "."))
    unit_key = normalize_key(unit or "")
    if unit_key in {"k", "nghin", "ngan", "thousand"}:
        return int(number * 1_000)
    if unit_key in {"tr", "trieu", "m", "cu", "million", "mil", "mio"}:
        return int(number * 1_000_000)
    return int(number)


def extract_budget_bounds(text: str | None) -> tuple[int | None, int | None]:
    norm = normalize_key(text or "")
    if not norm:
        return None, None

    compact = re.search(r"(?<!\d)(\d+)\s*(tr|trieu|m|cu|million|mil|mio)\s*(\d{1,2})(?!\d)", norm)
    if compact:
        left = int(compact.group(1)) * 1_000_000
        right = compact.group(3)
        extra = int(right) * (100_000 if len(right) == 1 else 10_000)
        amount = left + extra
        return None, amount

    range_match = re.search(
        rf"(?<!\d)(\d+(?:[.,]\d+)?)\s*({MONEY_UNITS})?\s*(?:-|den|toi|tới|đến|~)\s*(\d+(?:[.,]\d+)?)\s*({MONEY_UNITS})(?!\w)",
        norm,
    )
    if range_match:
        unit_left = range_match.group(2) or range_match.group(4)
        left = _money_to_vnd(range_match.group(1), unit_left)
        right = _money_to_vnd(range_match.group(3), range_match.group(4))
        return min(left, right), max(left, right)

    money = re.search(rf"(?<!\d)(\d+(?:[.,]\d+)?)\s*({MONEY_UNITS})(?!\w)", norm)
    if money:
        amount = _money_to_vnd(money.group(1), money.group(2))
        before = norm[max(0, money.start() - 36):money.start()]
        if re.search(r"\b(tu|tren|it nhat|min|from|at least)\b", before):
            return amount, None
        return None, amount

    full_vnd = re.search(r"(?<!\d)(\d{6,9})(?!\d)", norm)
    if full_vnd:
        return None, int(full_vnd.group(1))

    return None, None


def normalize_area(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = normalize_key(value)
    if not key:
        return None
    return AREA_ALIASES.get(key, value.strip().lower())


def _area_from_candidates(fallback_result: dict[str, Any] | None) -> str | None:
    if (fallback_result or {}).get("location_status") != "unsupported":
        return None
    for candidate in (fallback_result or {}).get("location_candidates", []) or []:
        area = normalize_area(candidate.get("canonical_area"))
        if area:
            return area
    return None


def normalize_preferred_type(*values: Any, raw_text: str = "") -> str | None:
    if len(find_type_candidates(raw_text)) > 1 and has_type_choice_connector(raw_text):
        return None

    for value in values:
        if isinstance(value, str):
            key = normalize_key(value)
            mapped = TYPE_ALIASES.get(key)
            if mapped in ALLOWED_TYPES:
                return mapped

    norm = normalize_key(raw_text)
    for alias, mapped in TYPE_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(normalize_key(alias))}(?!\w)", norm):
            return mapped
    return None


def _mapped_list(values: list[str], aliases: dict[str, str], allowed: set[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        key = normalize_key(value)
        mapped = aliases.get(key, key)
        if mapped in allowed:
            normalized.append(mapped)
    return _unique(normalized)


def _is_negated(norm_text: str, start: int) -> bool:
    window = norm_text[max(0, start - 32):start]
    return bool(re.search(r"\b(khong can|ko can|khong muon|ko muon|khong|no need|dont need|don't need)\b", window))


def _scan_aliases(raw_text: str, aliases: dict[str, str], allowed: set[str], *, allow_negation: bool = False) -> list[str]:
    norm = normalize_key(raw_text)
    found: list[str] = []
    for alias, mapped in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        alias_key = normalize_key(alias)
        for match in re.finditer(rf"(?<!\w){re.escape(alias_key)}(?!\w)", norm):
            if allow_negation and _is_negated(norm, match.start()):
                continue
            if mapped in allowed:
                found.append(mapped)
            break
    return _unique(found)


def _strict_supported_areas() -> bool:
    value = os.getenv("CHAT_API_STRICT_SUPPORTED_AREAS", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _fallback_question(missing_slots: list[str], locale: str, slots: dict[str, Any]) -> str | None:
    if not missing_slots:
        return None
    missing = set(missing_slots)
    if locale == "en":
        if missing == {"area", "budget", "guest_count"}:
            return "Where do you want to stay, what is your max budget per night, and how many guests?"
        if missing == {"area", "guest_count"}:
            return "Where do you want to stay and how many guests?"
        if missing == {"area", "budget"}:
            return "Where do you want to stay and what is your max budget per night?"
        if missing == {"budget", "guest_count"}:
            return "What is your max budget per night and how many guests?"
    else:
        if missing == {"area", "budget", "guest_count"}:
            return "Bạn muốn ở khu vực nào, ngân sách tối đa khoảng bao nhiêu và đi mấy người?"
        if missing == {"area", "guest_count"}:
            return "Bạn muốn ở khu vực nào và đi mấy người?"
        if missing == {"area", "budget"}:
            return "Bạn muốn ở khu vực nào và ngân sách tối đa khoảng bao nhiêu VND/đêm?"
        if missing == {"budget", "guest_count"}:
            return "Ngân sách tối đa khoảng bao nhiêu VND/đêm và bạn đi mấy người?"
    questions = build_suggested_questions(
        missing_slots=missing_slots,
        locale=locale,
        should_ask_optional=False,
        slots=slots,
    )
    return questions[0] if questions else None


def normalize_parsed_result(
    model_payload: dict[str, Any] | None,
    *,
    raw_text: str,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
    fallback_result: dict[str, Any] | None = None,
    parser_mode: str = "hf_transformers",
) -> dict[str, Any]:
    model_payload = model_payload or {}
    model_slots = model_payload.get("slots") if isinstance(model_payload.get("slots"), dict) else {}
    fallback_slots = (fallback_result or {}).get("slots") or {}
    context_slots = context_slots or {}

    slots = empty_slots()

    fallback_area = normalize_area(fallback_slots.get("area")) or _area_from_candidates(fallback_result)
    context_area = normalize_area(context_slots.get("area"))
    model_area = normalize_area(model_slots.get("area"))
    slots["area"] = fallback_area or model_area or context_area

    text_budget_min, text_budget_max = extract_budget_bounds(raw_text)
    slots["budget_min"] = (
        text_budget_min
        or _as_int(model_slots.get("budget_min"))
        or _as_int(fallback_slots.get("budget_min"))
        or _as_int(context_slots.get("budget_min"))
    )
    slots["budget_max"] = (
        text_budget_max
        or _as_int(model_slots.get("budget_max"))
        or _as_int(model_slots.get("budget"))
        or _as_int(fallback_slots.get("budget_max"))
        or _as_int(fallback_slots.get("budget"))
        or _as_int(context_slots.get("budget_max"))
        or _as_int(context_slots.get("budget"))
    )
    slots["budget"] = slots["budget_max"]

    slots["guest_count"] = (
        _as_int(fallback_slots.get("guest_count"))
        or extract_guest_count(raw_text)
        or _as_int(model_slots.get("guest_count"))
        or _as_int(context_slots.get("guest_count"))
    )

    slots["preferred_type"] = normalize_preferred_type(
        fallback_slots.get("preferred_type"),
        model_slots.get("preferred_type"),
        context_slots.get("preferred_type"),
        raw_text=raw_text,
    )

    model_amenities = _mapped_list(_as_list(model_slots.get("required_amenities")), AMENITY_ALIASES, ALLOWED_AMENITIES)
    fallback_amenities = _mapped_list(_as_list(fallback_slots.get("required_amenities")), AMENITY_ALIASES, ALLOWED_AMENITIES)
    scanned_amenities = _scan_aliases(raw_text, AMENITY_ALIASES, ALLOWED_AMENITIES, allow_negation=True)
    slots["required_amenities"] = _unique(fallback_amenities + model_amenities + extract_required_amenities(raw_text) + scanned_amenities)

    model_priorities = _mapped_list(_as_list(model_slots.get("priorities")), PRIORITY_ALIASES, ALLOWED_PRIORITIES)
    fallback_priorities = _mapped_list(_as_list(fallback_slots.get("priorities")), PRIORITY_ALIASES, ALLOWED_PRIORITIES)
    scanned_priorities = _scan_aliases(raw_text, PRIORITY_ALIASES, ALLOWED_PRIORITIES, allow_negation=True)
    slots["priorities"] = _unique(fallback_priorities + model_priorities + extract_priorities(raw_text) + scanned_priorities)

    model_special = _mapped_list(_as_list(model_slots.get("special_requirements")), SPECIAL_ALIASES, ALLOWED_SPECIAL_REQUIREMENTS)
    fallback_special = _mapped_list(_as_list(fallback_slots.get("special_requirements")), SPECIAL_ALIASES, ALLOWED_SPECIAL_REQUIREMENTS)
    scanned_special = _scan_aliases(raw_text, SPECIAL_ALIASES, ALLOWED_SPECIAL_REQUIREMENTS)
    slots["special_requirements"] = _unique(fallback_special + model_special + extract_special_requirements(raw_text) + scanned_special)

    slots["trip_days"] = (
        _as_int(fallback_slots.get("trip_days"))
        or extract_trip_days(raw_text)
        or _as_int(model_slots.get("trip_days"))
        or _as_int(context_slots.get("trip_days"))
    )

    missing_slots = [
        key for key in CORE_MISSING_KEYS
        if (key == "budget" and not slots.get("budget_max")) or (key != "budget" and not slots.get(key))
    ]

    location_status = (fallback_result or {}).get("location_status") or ("ok" if slots["area"] else "unresolved")
    ready_for_recommendation = not missing_slots
    if _strict_supported_areas() and location_status != "ok":
        ready_for_recommendation = False
    if fallback_result and fallback_result.get("ready_for_recommendation") is False and not missing_slots:
        ready_for_recommendation = False

    follow_up_question = None
    if (
        fallback_result
        and fallback_result.get("ready_for_recommendation") is False
        and fallback_result.get("follow_up_question")
        and not missing_slots
    ):
        follow_up_question = fallback_result["follow_up_question"]
    elif location_status not in {"ok", "unresolved"} and (fallback_result or {}).get("follow_up_question"):
        follow_up_question = (fallback_result or {}).get("follow_up_question")
    elif (
        parser_mode != "hybrid_rule_fallback"
        and isinstance(model_payload.get("follow_up_question"), str)
        and model_payload["follow_up_question"].strip()
    ):
        follow_up_question = model_payload["follow_up_question"].strip()
    elif not ready_for_recommendation:
        follow_up_question = _fallback_question(missing_slots, locale, slots)

    return {
        "schema_version": SCHEMA_VERSION,
        "intent": INTENT_DEFAULT,
        "slots": slots,
        "missing_slots": missing_slots,
        "suggested_questions": [follow_up_question] if follow_up_question else [],
        "ready_for_recommendation": ready_for_recommendation,
        "should_ask_optional": bool((fallback_result or {}).get("should_ask_optional", False)),
        "follow_up_question": follow_up_question,
        "parser_mode": parser_mode,
        "location_status": location_status,
        "location_candidates": (fallback_result or {}).get("location_candidates", []),
        "canonical_area": slots["area"] if location_status == "ok" else (fallback_result or {}).get("canonical_area"),
    }
