from __future__ import annotations

import logging
import os
import re
from typing import Any

from django.conf import settings

from .convenience_policy import TERMINAL_INTENTS, decide_user_effort_policy
from .constants import NUMBER_WORDS
from .clarification_manager import build_clarification_payload
from .domain_router import classify_message
from .extractors import (
    find_unsupported_type_candidates,
)
from .filter_tree import (
    build_filter_tree,
    has_explicit_anywhere,
    should_ignore_numeric_location_match,
    soft_filter_summary,
)
from .fuzzy_location import resolve_location_fuzzy
from .gate import evaluate_parse_gate
from .location_gazetteer import load_supported_locations
from .location_resolver import resolve_location
from .normalizers import normalize_key, normalize_text
from .protected_spans import public_protected_spans
from .questions import build_suggested_questions
from .response_generator import ResponseGenerator
from .response_templates import (
    build_conflict_message,
    build_explicit_confirmation_message,
    build_full_message,
    build_goodbye_message,
    build_greeting_message,
    build_help_message,
    build_implicit_confirmation_message,
    build_multiple_choice_message,
    build_off_topic_message,
    build_partial_message,
    build_thanks_message,
    build_unknown_message,
    build_unresolved_location_message,
    build_unresolved_place_message,
    build_unsupported_message,
)
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .search_origin import build_search_origin
from .slot_pipeline import build_slot_parse_context
from .slot_validator import core_missing_slots, extract_slots_from_text, merge_slot_context, validate_slots
from .suggestion_catalog import detect_nearby_poi
from .text_normalizer import normalize_user_text
from .validators import validate_and_normalize_slots

USE_NER_FALLBACK = os.getenv("CHAT_API_USE_NER", "0") == "1"
INCLUDE_PARSE_DIAGNOSTICS = os.getenv("CHAT_API_INCLUDE_DIAGNOSTICS", "0") == "1"
logger = logging.getLogger(__name__)

CONFIRM_CORE_KEYS = ("area", "guest_count", "budget", "trip_days")
CONFIRM_SKIP_KEYS = {
    "budget_min",
    "budget_max",
    "user_location",
    "use_current_location",
    "accommodation_type",
    "accommodation_types",
    "location_phrase",
    "location_mode",
    "canonical_area",
    "selected_place",
    "raw_preferred_type",
    "unsupported_preferred_type",
    "search_intent",
    "type_choice_multiple",
    "search_radius_km",
    "nearby_place",
}
RECOMMENDATION_SIGNAL_KEYS = (
    "area",
    "guest_count",
    "budget",
    "trip_days",
    "preferred_type",
    "accommodation_type",
    "accommodation_types",
    "required_amenities",
    "priorities",
    "special_requirements",
    "room_count",
    "rating",
)
RECOMMENDATION_ALLOWED_LOCATION_STATUSES = {"ok", "unresolved"}
HCM_DISTRICT_MIN = 1
HCM_DISTRICT_MAX = 12
HCM_DISTRICT_WORD_PATTERN = (
    r"muoi\s+(?:mot|hai)|eleven|twelve|"
    r"mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|"
    r"one|two|three|four|five|six|seven|eight|nine|ten"
)
HCM_DISTRICT_COMPOUND_WORDS = {
    "muoi mot": 11,
    "muoi hai": 12,
    "eleven": 11,
    "twelve": 12,
}
GENERIC_RECOMMENDATION_PRIORITIES = ("high_rating",)
CONFIRM_LABELS = {
    "area": "Khu vực",
    "guest_count": "Số người",
    "budget": "Ngân sách",
    "budget_min": "Ngân sách tối thiểu",
    "budget_max": "Ngân sách tối đa",
    "trip_days": "Số ngày",
    "preferred_type": "Loại chỗ ở",
    "accommodation_type": "Loại chỗ ở",
    "accommodation_types": "Loại chỗ ở",
    "required_amenities": "Tiện nghi yêu cầu",
    "priorities": "Ưu tiên",
    "special_requirements": "Yêu cầu đặc biệt",
    "check_in": "Ngày nhận phòng",
    "check_out": "Ngày trả phòng",
    "room_count": "Số phòng",
    "rating": "Đánh giá tối thiểu",
    "location_phrase": "Địa điểm",
    "location_mode": "Kiểu vị trí",
    "work_friendly": "Phù hợp làm việc",
    "baby_friendly": "Phù hợp trẻ em",
    "pet_friendly": "Cho phép thú cưng",
    "near_center": "Gần trung tâm",
    "quiet": "Yên tĩnh",
    "pool": "Hồ bơi",
    "wifi": "Wifi",
    "parking": "Đỗ xe",
    "breakfast": "Ăn sáng",
}
CONFIRM_VALUE_LABELS = {
    "hotel": "Khách sạn",
    "homestay": "Homestay",
    "hostel": "Hostel",
    "apartment": "Căn hộ",
    "resort": "Resort",
    "villa": "Biệt thự",
    "wifi": "Wifi",
    "pool": "Hồ bơi",
    "parking": "Đỗ xe",
    "air_conditioner": "Điều hòa",
    "breakfast": "Ăn sáng",
    "balcony": "Ban công",
    "bathtub": "Bồn tắm",
    "kitchen": "Bếp",
    "washing_machine": "Máy giặt",
    "near_center": "Gần trung tâm",
    "near_beach": "Gần biển",
    "cheap": "Giá tốt",
    "quiet": "Yên tĩnh",
    "high_rating": "Đánh giá cao",
    "nice_view": "View đẹp",
    "clean": "Sạch sẽ",
    "convenient": "Tiện lợi",
    "baby_friendly": "Phù hợp trẻ em",
    "elderly_friendly": "Phù hợp người lớn tuổi",
    "pet_friendly": "Cho phép thú cưng",
    "work_friendly": "Phù hợp làm việc",
    "family_friendly": "Phù hợp gia đình",
    "couple_friendly": "Phù hợp cặp đôi",
    "private": "Riêng tư",
    "safe_area": "Khu vực an toàn",
}
HIDDEN_CONFIRM_PRIORITIES = {"high_rating"}


def _format_hcm_district(raw_number: str) -> str | None:
    district = int(raw_number)
    if HCM_DISTRICT_MIN <= district <= HCM_DISTRICT_MAX:
        return f"Quận {district}"
    return None


def _extract_area_fallback(text: str) -> str | None:
    text_lower = text.lower().strip()
    text_key = normalize_key(text)

    # Bắt các kiểu: quận 1, quan 1, q1, q.1, q 1, district 1
    match = re.search(r"\b(?:quận|quan|q\.?|district)\s*(\d{1,2})(?!\d)\b", text_lower)
    if match:
        return _format_hcm_district(match.group(1))

    # Bắt cách nói bằng giọng: "quận hai", "quan muoi hai", "district two".
    match = re.search(rf"\b(?:quan|q\.?|district|dist)\s+({HCM_DISTRICT_WORD_PATTERN})(?!\w)\b", text_key)
    if match:
        word_key = normalize_key(match.group(1))
        district = HCM_DISTRICT_COMPOUND_WORDS.get(word_key) or NUMBER_WORDS.get(word_key)
        if district is not None:
            return _format_hcm_district(str(district))

    # Một số khu vực phổ biến
    if "thủ đức" in text_lower or "thu duc" in text_lower:
        return "Thủ Đức"

    if "gò vấp" in text_lower or "go vap" in text_lower:
        return "Gò Vấp"

    if "bình thạnh" in text_lower or "binh thanh" in text_lower:
        return "Bình Thạnh"

    if "tân bình" in text_lower or "tan binh" in text_lower:
        return "Tân Bình"

    if "phú nhuận" in text_lower or "phu nhuan" in text_lower:
        return "Phú Nhuận"

    return None


def _is_general_recommendation_request(text: str) -> bool:
    norm = normalize_key(text)
    if not norm:
        return False

    intent_patterns = [
        r"\b(?:toi|minh|tui|em|anh|chi)\s+(?:muon|can|dinh|tinh)\s+di(?:\s+(?:choi|du lich|nghi|nghi duong|cong tac))?(?:\s+thoi)?\b",
        r"\b(?:muon|can|dinh|tinh)\s+di\s+(?:choi|du lich|nghi|nghi duong|cong tac)(?:\s+thoi)?\b",
        r"\bdi\s+(?:choi|du lich|nghi|nghi duong)(?:\s+thoi)?\b",
        r"\b(?:choi|du lich|nghi)\s+thoi\b",
        r"\b(?:goi y|de xuat|tim|cho minh|cho toi)\s+(?:khach san|cho o|phong)?\s*(?:tot|tot nhat|chat luong|xin|rating cao|danh gia cao)\b",
    ]
    return any(re.search(pattern, norm) for pattern in intent_patterns)


def _apply_general_recommendation_defaults(slots: dict[str, Any], text: str) -> None:
    if not _is_general_recommendation_request(text):
        return


def merge_context(slots_new: dict[str, Any], context_slots: dict[str, Any] | None) -> dict[str, Any]:
    if not context_slots:
        return slots_new

    merged = dict(context_slots)

    for k in ["area", "budget", "budget_min", "budget_max", "guest_count", "preferred_type", "accommodation_type", "trip_days"]:
        v = slots_new.get(k)
        if v is not None:
            merged[k] = v

    for k in ["accommodation_types", "required_amenities", "priorities", "special_requirements"]:
        base = merged.get(k) or []
        add = slots_new.get(k) or []
        merged[k] = list(dict.fromkeys(list(base) + list(add)))

    return merged


def _extract_bare_count_reply(text: str) -> int | None:
    token = normalize_key(text).strip(" .,!?:;-/")
    if not token:
        return None
    if re.fullmatch(r"\d{1,2}", token):
        return int(token)
    return NUMBER_WORDS.get(token)


def _first_missing_core_slot(context_slots: dict[str, Any] | None) -> str | None:
    if not context_slots:
        return None

    for key in CORE_SLOTS:
        if key == "budget":
            if not (context_slots.get("budget") or context_slots.get("budget_max")):
                return key
        elif not context_slots.get(key):
            return key

    return None


def _apply_bare_count_follow_up(
    slots_partial: dict[str, Any],
    raw: str,
    context_slots: dict[str, Any] | None,
) -> None:
    value = _extract_bare_count_reply(raw)
    if value is None:
        return

    first_missing = _first_missing_core_slot(context_slots)
    if first_missing == "guest_count" and slots_partial.get("guest_count") is None:
        slots_partial["guest_count"] = value
    elif first_missing == "trip_days" and slots_partial.get("trip_days") is None:
        slots_partial["trip_days"] = value


def _include_debug_metadata(include_debug: bool | None) -> bool:
    if include_debug is not None:
        return bool(include_debug)
    return bool(getattr(settings, "DEBUG", False))


def _attach_parse_debug_metadata(
    result: dict[str, Any],
    *,
    slot_parse_context: dict[str, Any],
    location: dict[str, Any] | None = None,
) -> None:
    location = location or {}
    location_intent = slot_parse_context.get("location_intent") or {}
    result["debug_metadata"] = {
        "raw_text": slot_parse_context.get("raw_text") or "",
        "normalized_text": slot_parse_context.get("normalized_text") or "",
        "protected_spans": slot_parse_context.get("protected_spans") or [],
        "remaining_text_for_location": slot_parse_context.get("remaining_text_for_location") or "",
        "location_candidate": slot_parse_context.get("location_candidate"),
        "location_confidence": slot_parse_context.get("location_candidate_confidence") or 0.0,
        "location_mode": location.get("location_mode") or location_intent.get("mode_hint") or "unknown",
        "location_intent": bool(
            location_intent.get("should_resolve")
            or location_intent.get("mode_hint") == "city_center"
            or location_intent.get("ambiguous_location")
        ),
        "geocoder_called": bool(location.get("geocoder_called")),
        "geocoder_reason": location.get("geocoder_reason")
        or slot_parse_context.get("geocoder_reason")
        or "no_location_intent",
        "geocoder_block_reason": location.get("geocoder_reason")
        or slot_parse_context.get("geocoder_reason")
        or "no_location_intent",
        "location_source": location.get("location_source") or "none",
        "cache_hit": bool(location.get("cache_hit")),
        "rejected_reason": _first_rejected_reason(location.get("rejected_geocoder_results")),
        "rejected_geocoder_results": location.get("rejected_geocoder_results") or [],
        "area_match": bool(location.get("area_match")),
    }


def _first_rejected_reason(rejected_results: Any) -> str | None:
    if not isinstance(rejected_results, list) or not rejected_results:
        return None
    first = rejected_results[0]
    if isinstance(first, dict):
        return first.get("reason") or first.get("rejected_reason")
    return None


def _has_confirm_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _confirm_label(key: str) -> str:
    return CONFIRM_LABELS.get(key, key.replace("_", " ").title())


def _confirm_value(slots: dict[str, Any], key: str) -> Any:
    if key == "budget":
        return slots.get("budget") or slots.get("budget_max") or slots.get("budget_min")
    return slots.get(key)


def _display_confirm_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(_display_confirm_value(item)) for item in value)
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, str):
        return CONFIRM_VALUE_LABELS.get(value, value)
    return value


def _visible_confirm_value(key: str, value: Any) -> Any:
    if key == "priorities" and isinstance(value, (list, tuple, set)):
        return [item for item in value if item not in HIDDEN_CONFIRM_PRIORITIES]
    return value


def has_recommendation_signal(slots: dict[str, Any] | None) -> bool:
    slots = slots or {}
    return any(
        _has_confirm_value(_confirm_value(slots, key))
        for key in RECOMMENDATION_SIGNAL_KEYS
    )


def _attach_filter_tree_payload(result: dict[str, Any], text: str) -> None:
    tree = build_filter_tree(
        text=text,
        slots=result.get("slots") or {},
        location_result=result,
    )
    tree_dict = tree.to_dict()
    location = tree_dict["location"]
    slots = dict(result.get("slots") or {})

    if result.get("debug_metadata"):
        result["debug_metadata"].update(
            {
                "location_candidate": location.get("location_phrase")
                or result["debug_metadata"].get("location_candidate"),
                "location_mode": location.get("mode") or result["debug_metadata"].get("location_mode"),
                "geocoder_called": bool(location.get("geocoder_called")),
                "geocoder_reason": location.get("geocoder_reason")
                or result["debug_metadata"].get("geocoder_reason"),
                "geocoder_block_reason": location.get("geocoder_reason")
                or result["debug_metadata"].get("geocoder_block_reason"),
                "location_source": location.get("location_source")
                or result["debug_metadata"].get("location_source")
                or "none",
                "cache_hit": bool(location.get("cache_hit")),
                "location_confidence": location.get("confidence")
                or result["debug_metadata"].get("location_confidence")
                or 0.0,
                "rejected_reason": _first_rejected_reason(location.get("rejected_geocoder_results")),
                "rejected_geocoder_results": location.get("rejected_geocoder_results") or [],
                "area_match": bool(location.get("area_match")),
            }
        )

    if location.get("mode") == "anywhere":
        slots["area"] = None
        result["canonical_area"] = None
    elif location.get("mode") == "near_anchor":
        if location.get("canonical_area"):
            slots["area"] = location["canonical_area"]
            result["canonical_area"] = location["canonical_area"]
        elif location.get("anchor_kind") not in {"district", "city"}:
            slots["area"] = None
            result["canonical_area"] = None
    elif location.get("mode") == "area" and location.get("canonical_area"):
        slots["area"] = location["canonical_area"]
        result["canonical_area"] = location["canonical_area"]
    elif location.get("mode") == "city_center" and location.get("canonical_area"):
        slots["area"] = location["canonical_area"]
        result["canonical_area"] = location["canonical_area"]

    unresolved_location = bool(location.get("unresolved_location"))
    if location.get("mode") in {"near_anchor", "city_center"} and (
        location.get("anchor_lat") is None or location.get("anchor_lon") is None
    ):
        unresolved_location = True
    if location.get("mode") == "multiple_choice":
        slots["area"] = None
        result["canonical_area"] = None
        result["location_status"] = "multiple_choice"
        unresolved_location = False
    elif unresolved_location:
        slots["area"] = None
        result["canonical_area"] = None
        result["location_status"] = "ambiguous" if location.get("needs_city_clarification") else "unresolved"
    elif (
        location.get("mode") in {"near_anchor", "city_center"}
        and location.get("anchor_lat") is not None
        and location.get("anchor_lon") is not None
        and result.get("location_status") not in {"conflict", "multiple_choice"}
    ):
        result["location_status"] = "ok"

    result["slots"] = slots
    result["filter_tree"] = tree_dict
    result["soft_filter_summary"] = soft_filter_summary(tree_dict)
    result["available_slots"] = tree_dict["available_slots"]
    result["missing_filter_slots"] = tree_dict["missing_slots"]
    result["partial_intent"] = tree_dict["partial_intent"]
    result["success"] = result.get("conversation_intent") != "unknown"

    result["location_mode"] = location.get("mode")
    result["location_phrase"] = location.get("location_phrase")
    result["explicit_anywhere"] = bool(location.get("explicit_anywhere"))
    result["anchor_name"] = location.get("anchor_name")
    result["anchor_kind"] = location.get("anchor_kind")
    result["anchor_lat"] = location.get("anchor_lat")
    result["anchor_lon"] = location.get("anchor_lon")
    result["anchor_radius_km"] = location.get("anchor_radius_km")
    result["search_radius_km"] = location.get("search_radius_km") or slots.get("search_radius_km")
    result["provider"] = location.get("provider")
    result["resolved_place"] = location.get("resolved_place")
    result["location_display_label"] = location.get("location_display_label")
    result["map_area"] = location.get("map_area")
    result["map_display_name"] = location.get("map_display_name")
    result["map_address"] = location.get("map_address") or {}
    result["geocode_query"] = location.get("geocode_query")
    result["geocoder_queries"] = location.get("geocoder_queries") or []
    result["geocoder_called"] = bool(location.get("geocoder_called"))
    result["geocoder_reason"] = location.get("geocoder_reason")
    result["rejected_geocoder_results"] = location.get("rejected_geocoder_results") or []
    result["rejected_reason"] = _first_rejected_reason(result["rejected_geocoder_results"])
    result["cache_hit"] = bool(location.get("cache_hit"))
    result["needs_city_clarification"] = bool(location.get("needs_city_clarification"))
    result["ambiguous_location"] = bool(location.get("ambiguous_location"))
    result["ambiguous_location_question"] = location.get("ambiguous_location_question")
    result["nearby_place"] = location.get("nearby_place") or result.get("nearby_place")
    result["location_candidates"] = location.get("location_candidates") or result.get("location_candidates") or []
    result["area_match"] = bool(location.get("area_match"))
    result["unresolved_location"] = unresolved_location
    if location.get("mode"):
        slots["location_mode"] = location.get("mode")
    if location.get("location_phrase"):
        slots["location_phrase"] = location.get("location_phrase")
    if result.get("nearby_place"):
        slots["nearby_place"] = result.get("nearby_place")
    if result.get("search_radius_km") is not None:
        slots["search_radius_km"] = result.get("search_radius_km")
    if slots.get("preferred_type") and not slots.get("accommodation_type"):
        slots["accommodation_type"] = slots.get("preferred_type")
    if slots.get("preferred_type") and not slots.get("accommodation_types"):
        slots["accommodation_types"] = [slots.get("preferred_type")]
    result["accommodation_type"] = slots.get("accommodation_type") or slots.get("preferred_type")
    result["accommodation_types"] = slots.get("accommodation_types") or (
        [result["accommodation_type"]] if result.get("accommodation_type") else []
    )
    if location.get("location_source") and location.get("location_source") != "none":
        result["location_source"] = location.get("location_source")
    if location.get("confidence"):
        result["location_confidence"] = location.get("confidence")


def build_confirm_table(slots: dict[str, Any]) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    included: set[str] = set()

    for key in CONFIRM_CORE_KEYS:
        value = _visible_confirm_value(key, _confirm_value(slots, key))
        if _has_confirm_value(value):
            table.append({
                "key": key,
                "label": _confirm_label(key),
                "value": value,
                "display_value": _display_budget_confirm_value(slots) if key == "budget" else _display_confirm_value(value),
            })
            included.add(key)

    accommodation_types = _normalized_confirm_types(slots)
    if accommodation_types:
        key = "preferred_type" if len(accommodation_types) == 1 else "accommodation_types"
        value: Any = accommodation_types[0] if len(accommodation_types) == 1 else accommodation_types
        table.append({
            "key": key,
            "label": _confirm_label(key),
            "value": value,
            "display_value": _display_confirm_value(value),
        })
        included.update({"preferred_type", "accommodation_type", "accommodation_types"})

    for key, value in (slots or {}).items():
        if key in included or key in CONFIRM_SKIP_KEYS:
            continue
        value = _visible_confirm_value(key, value)
        if _has_confirm_value(value):
            table.append({
                "key": key,
                "label": _confirm_label(key),
                "value": value,
                "display_value": _display_confirm_value(value),
            })

    return table


def _normalized_confirm_types(slots: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw_types = slots.get("accommodation_types") or []
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    if isinstance(raw_types, (list, tuple, set)):
        values.extend(str(item).strip() for item in raw_types if str(item).strip())
    for key in ("preferred_type", "accommodation_type"):
        value = slots.get(key)
        if value:
            values.append(str(value).strip())
    return list(dict.fromkeys(value for value in values if value))


def _display_budget_confirm_value(slots: dict[str, Any]) -> str:
    budget_min = slots.get("budget_min")
    budget_max = slots.get("budget_max") or slots.get("budget")
    if budget_min and budget_max:
        return f"{_format_vnd(budget_min)} - {_format_vnd(budget_max)}/đêm"
    if budget_min:
        return f"Từ {_format_vnd(budget_min)}/đêm"
    if budget_max:
        return f"Tối đa {_format_vnd(budget_max)}/đêm"
    return ""


def _format_vnd(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".") + "đ"
    except (TypeError, ValueError):
        return str(value)


def _location_confirm_value(result: dict[str, Any]) -> str:
    location_mode = result.get("location_mode") or (result.get("filter_tree") or {}).get("location", {}).get("mode")
    slots = result.get("slots") or {}

    if location_mode == "anywhere":
        return "Không giới hạn khu vực"
    if location_mode == "city_center":
        return result.get("location_display_label") or result.get("anchor_name") or "trung tâm thành phố"
    if location_mode in {"near_anchor", "near_user"}:
        return result.get("location_display_label") or result.get("anchor_name") or ""
    if location_mode == "area":
        return result.get("canonical_area") or slots.get("area") or result.get("location_display_label") or ""
    return ""


def _prepend_location_confirm_item(result: dict[str, Any], table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(item.get("key") in {"area", "location"} for item in table):
        return table

    location_value = _location_confirm_value(result)
    if not location_value:
        return table

    return [
        {
            "key": "location",
            "label": "Khu vực",
            "value": location_value,
            "display_value": location_value,
        },
        *table,
    ]


def _message_slots_with_location(result: dict[str, Any]) -> dict[str, Any]:
    slots = dict(result.get("slots") or {})
    if slots.get("area"):
        return slots

    location_value = _location_confirm_value(result)
    if not location_value:
        return slots

    if location_value.startswith("gần "):
        location_value = f"khu vực {location_value}"
    slots["area"] = location_value
    return slots


def add_confirmation_payload(
    result: dict[str, Any],
    *,
    locale: str = "vi",
    require_confirmation: bool = True,
) -> dict[str, Any]:
    result["awaiting_confirmation"] = False
    result["confirmation_required"] = False
    result.pop("confirm_table", None)
    result.pop("confirmation_heading", None)
    result.pop("confirmation_prompt", None)
    result.pop("confirmation_options", None)

    confirm_table = build_confirm_table(result.get("slots") or {})
    confirm_table = _prepend_location_confirm_item(result, confirm_table)

    if confirm_table:
        result["awaiting_confirmation"] = require_confirmation
        result["confirmation_required"] = require_confirmation
        result["confirm_table"] = confirm_table
        result["confirmation_heading"] = (
            "Confirm information"
            if locale == "en"
            else ("Xác nhận thông tin" if require_confirmation else "Thông tin mình đã hiểu")
        )
        result["confirmation_prompt"] = (
            "Do you want to add more information?"
            if locale == "en"
            else (
                "Bạn muốn bổ sung thêm thông tin không?"
                if require_confirmation
                else "Mình sẽ gợi ý trước; bạn có thể bổ sung thêm để lọc sát hơn."
            )
        )
        result["confirmation_options"] = [
            {"id": "add_more", "label": "Tôi muốn bổ sung thêm thông tin"},
        ]

    return result


def parse_user_text_rule_based(
    text: str,
    *,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
    include_debug: bool | None = None,
) -> dict[str, Any]:
    normalized = normalize_user_text(text)
    raw = normalized["normalized_text"]
    slot_parse_context = build_slot_parse_context(text)
    router = classify_message(text, context_slots=context_slots, locale=locale)
    if (
        router.get("intent") == "unknown"
        and any(span.get("type") == "generic_lodging_phrase" for span in slot_parse_context.get("protected_spans") or [])
    ):
        router = {**router, "intent": "recommend_accommodation", "reason": "generic_lodging_phrase"}

    if router["intent"] in TERMINAL_INTENTS and router["intent"] != "unknown":
        response = _terminal_response(router, normalized, context_slots=context_slots)
        response["protected_spans"] = public_protected_spans(slot_parse_context)
        if _include_debug_metadata(include_debug):
            _attach_parse_debug_metadata(response, slot_parse_context=slot_parse_context)
        return _finalize_convenience_response(response, text, router=router, normalized=normalized)

    generic_nearby_poi = detect_nearby_poi(text)
    if generic_nearby_poi:
        location = _generic_nearby_poi_location(generic_nearby_poi)
    else:
        location = _resolve_location_pipeline(
            text,
            locale=locale,
            context_slots=context_slots,
            prefer_context=router["intent"] == "clarify_slot",
            slot_parse_context=slot_parse_context,
        )
    slots_partial = extract_slots_from_text(
        text,
        canonical_area=location.get("canonical_area"),
        slot_parse_context=slot_parse_context,
    )
    _apply_bare_count_follow_up(slots_partial, raw, context_slots)

    replace_location_context = bool(location.get("_from_text"))
    replace_area = bool(replace_location_context and location.get("location_status") == "ok")
    slots_partial = merge_slot_context(
        slots_partial,
        context_slots,
        replace_area=replace_area,
        replace_location_context=replace_location_context,
    )
    slots = validate_slots(slots_partial)

    if location["location_status"] == "ok":
        slots["area"] = location["canonical_area"]
    elif location.get("_from_context") and slots.get("area"):
        location["location_status"] = "ok"
        location["canonical_area"] = slots["area"]
        location["location_confidence"] = 1.0
        location["location_source"] = "context"
    elif location["location_status"] in {"unresolved", "unsupported", "ambiguous", "multiple_choice", "conflict"}:
        slots["area"] = None

    _apply_general_recommendation_defaults(slots, raw)
    if router["intent"] == "recommend_accommodation":
        slots["search_intent"] = "find_accommodation"

    missing_slots = core_missing_slots(slots)
    gate = evaluate_parse_gate(raw, slots, locale=locale, location_status=location["location_status"])
    should_ask_optional = (
        location["location_status"] == "ok"
        and not slots.get("preferred_type")
        and not slots.get("required_amenities")
        and not slots.get("priorities")
        and not slots.get("special_requirements")
    )
    suggested_questions = build_suggested_questions(
        missing_slots=missing_slots,
        locale=locale,
        should_ask_optional=should_ask_optional,
        slots=slots,
    )
    if gate.get("follow_up_question"):
        suggested_questions = [gate["follow_up_question"]]

    response = {
        "schema_version": SCHEMA_VERSION,
        "intent": INTENT_DEFAULT,
        "conversation_intent": router["intent"],
        "slots": slots,
        "missing_slots": missing_slots,
        "suggested_questions": suggested_questions,
        "ready_for_recommendation": False,
        "should_ask_optional": should_ask_optional,
        "follow_up_question": suggested_questions[0] if suggested_questions else None,
        "parser_mode": "deterministic_fuzzy_fast",
        "location_status": location["location_status"],
        "location_candidates": location.get("location_candidates", []),
        "canonical_area": location.get("canonical_area"),
        "location_confidence": location.get("location_confidence", 0.0),
        "location_source": location.get("location_source", "none"),
        "matched_text": location.get("matched_text"),
        "assumptions": [],
        "used_default_slots": {},
        "llm_called": False,
        "router": router,
        "protected_spans": public_protected_spans(slot_parse_context),
    }
    for key in (
        "location_mode",
        "location_phrase",
        "location_display_label",
        "anchor_name",
        "anchor_kind",
        "anchor_lat",
        "anchor_lon",
        "anchor_radius_km",
        "provider",
        "geocoder_called",
        "geocoder_reason",
        "rejected_geocoder_results",
        "needs_city_clarification",
        "ambiguous_location",
        "ambiguous_location_question",
        "nearby_place",
    ):
        if key in location:
            response[key] = location.get(key)

    if INCLUDE_PARSE_DIAGNOSTICS:
        response["diagnostics"] = {
            "router": router,
            "normalized_text": normalized["normalized_text"],
            "blocking_reasons": gate["blocking_reasons"],
            **gate["diagnostics"],
            "location": location.get("debug", {}),
        }
        unsupported_type_candidates = find_unsupported_type_candidates(raw)
        if unsupported_type_candidates:
            response["diagnostics"]["unsupported_type_candidates"] = unsupported_type_candidates

    if _include_debug_metadata(include_debug):
        _attach_parse_debug_metadata(response, slot_parse_context=slot_parse_context, location=location)

    return _finalize_convenience_response(response, text, router=router, normalized=normalized)


def _terminal_response(
    router: dict[str, Any],
    normalized: dict[str, Any],
    *,
    context_slots: dict[str, Any] | None,
) -> dict[str, Any]:
    slots = validate_slots(context_slots or {})
    intent = router["intent"]
    return {
        "schema_version": SCHEMA_VERSION,
        "intent": intent,
        "conversation_intent": intent,
        "slots": slots,
        "missing_slots": core_missing_slots(slots),
        "suggested_questions": [],
        "ready_for_recommendation": False,
        "should_ask_optional": False,
        "follow_up_question": None,
        "parser_mode": "domain_router",
        "location_status": "unresolved",
        "location_candidates": [],
        "canonical_area": None,
        "location_confidence": 0.0,
        "location_source": "none",
        "matched_text": None,
        "assumptions": [],
        "used_default_slots": {},
        "llm_called": False,
        "router": router,
    }


def _generic_nearby_poi_location(poi: dict[str, Any]) -> dict[str, Any]:
    label = str(poi.get("name") or "địa điểm")
    return {
        "location_status": "ambiguous",
        "location_candidates": [],
        "canonical_area": None,
        "location_confidence": 0.72,
        "location_source": "catalog_poi",
        "matched_text": poi.get("matched_alias") or label,
        "needs_confirmation": True,
        "confirmation_type": "explicit",
        "location_mode": "nearby_place",
        "location_phrase": label,
        "nearby_place": label,
        "ambiguous_location": True,
        "ambiguous_location_question": f"Bạn muốn gần {label} ở khu vực nào?",
        "geocoder_called": False,
        "geocoder_reason": "poi_category_needs_area",
        "debug": {"generic_nearby_poi": poi},
        "_from_text": True,
        "_from_context": False,
    }


def _resolve_location_pipeline(
    text: str,
    *,
    locale: str,
    context_slots: dict[str, Any] | None,
    prefer_context: bool = False,
    slot_parse_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    original_text = text
    slot_parse_context = slot_parse_context or build_slot_parse_context(text)
    location_intent = slot_parse_context.get("location_intent") or {}
    location_text = location_intent.get("resolve_text") or slot_parse_context.get("remaining_text_for_location") or ""
    supported_locations = load_supported_locations()
    context_area = (context_slots or {}).get("area") or (context_slots or {}).get("canonical_area")

    if has_explicit_anywhere(text):
        return {
            "location_status": "unresolved",
            "location_candidates": [],
            "canonical_area": None,
            "location_confidence": 0.98,
            "location_source": "explicit_anywhere",
            "matched_text": None,
            "debug": {"explicit_anywhere": True},
            "geocoder_called": False,
            "geocoder_reason": "explicit_anywhere",
            "area_match": False,
            "_from_text": True,
            "_from_context": False,
        }

    if location_intent.get("mode_hint") == "city_center":
        center = location_intent.get("city_center")
        if center:
            return {
                "location_status": "ok",
                "location_candidates": [],
                "canonical_area": center.get("canonical_area"),
                "location_confidence": center.get("confidence") or location_intent.get("confidence") or 0.93,
                "location_source": "semantic_city_center",
                "matched_text": location_intent.get("candidate") or "trung tâm thành phố",
                "needs_confirmation": False,
                "confirmation_type": "none",
                "debug": {"location_intent": location_intent},
                "location_mode": "city_center",
                "location_phrase": "trung tâm thành phố",
                "location_display_label": center.get("location_display_label"),
                "anchor_name": center.get("anchor_name"),
                "anchor_kind": "city_center",
                "anchor_lat": center.get("anchor_lat"),
                "anchor_lon": center.get("anchor_lon"),
                "anchor_radius_km": center.get("anchor_radius_km"),
                "provider": "semantic",
                "geocoder_called": False,
                "geocoder_reason": "abstract_city_center_location",
                "area_match": False,
                "rejected_geocoder_results": [],
                "_from_text": True,
                "_from_context": False,
            }

        return {
            "location_status": "ambiguous",
            "location_candidates": [],
            "canonical_area": None,
            "location_confidence": location_intent.get("confidence") or 0.72,
            "location_source": "semantic_city_center",
            "matched_text": location_intent.get("candidate") or "trung tâm thành phố",
            "needs_confirmation": True,
            "confirmation_type": "explicit",
            "debug": {"location_intent": location_intent},
            "location_mode": "city_center",
            "location_phrase": "trung tâm thành phố",
            "needs_city_clarification": True,
            "ambiguous_location": True,
            "ambiguous_location_question": "Bạn muốn trung tâm thành phố nào?",
            "geocoder_called": False,
            "geocoder_reason": "needs_city_for_city_center",
            "area_match": False,
            "rejected_geocoder_results": [],
            "_from_text": True,
            "_from_context": False,
        }

    if prefer_context and context_area:
        context_location = resolve_location_fuzzy(str(context_area), supported_locations)
        if context_location.get("location_status") == "ok":
            context_location["location_source"] = "context"
            context_location["location_confidence"] = 1.0
            context_location["geocoder_called"] = False
            context_location["geocoder_reason"] = "context_location"
            context_location["area_match"] = True
            context_location["_from_text"] = False
            context_location["_from_context"] = True
            return _sanitize_location_result(original_text, context_location)

    if location_intent.get("should_resolve") and location_intent.get("mode_hint") == "near_anchor":
        candidate = location_intent.get("candidate") or location_text
        legacy_location = resolve_location(normalize_text(str(location_text or candidate or "")), locale=locale)
        if legacy_location.get("location_status") in {"conflict", "multiple_choice"}:
            converted = _convert_legacy_location(legacy_location, supported_locations)
            converted["geocoder_reason"] = location_intent.get("reason") or "near_anchor_area_conflict"
            return converted
        return {
            "location_status": "unresolved",
            "location_candidates": [],
            "canonical_area": None,
            "location_confidence": location_intent.get("confidence") or 0.0,
            "location_source": "location_intent_gate",
            "matched_text": candidate,
            "needs_confirmation": False,
            "confirmation_type": "none",
            "debug": {
                "location_intent": location_intent,
                "remaining_text_for_location": slot_parse_context.get("remaining_text_for_location"),
            },
            "location_mode": "near_anchor",
            "location_phrase": candidate,
            "geocoder_called": False,
            "geocoder_reason": location_intent.get("reason") or "strong_near_anchor_or_place_phrase",
            "area_match": False,
            "_from_text": True,
            "_from_context": False,
        }

    if not location_intent.get("should_resolve"):
        if location_intent.get("ambiguous_location"):
            return {
                "location_status": "ambiguous",
                "location_candidates": location_intent.get("suggested_places") or [],
                "canonical_area": None,
                "location_confidence": location_intent.get("confidence") or 0.45,
                "location_source": "ambiguous_location_guard",
                "matched_text": location_intent.get("candidate"),
                "needs_confirmation": True,
                "confirmation_type": "explicit",
                "debug": {
                    "location_intent": location_intent,
                    "remaining_text_for_location": slot_parse_context.get("remaining_text_for_location"),
                },
                "ambiguous_location": True,
                "ambiguous_location_question": location_intent.get("ambiguous_location_question"),
                "geocoder_called": False,
                "geocoder_reason": "ambiguous_location",
                "area_match": False,
                "rejected_geocoder_results": [],
                "_from_text": True,
                "_from_context": False,
            }
        if context_area:
            context_location = resolve_location_fuzzy(str(context_area), supported_locations)
            if context_location.get("location_status") == "ok":
                context_location["location_source"] = "context"
                context_location["location_confidence"] = 1.0
                context_location["geocoder_called"] = False
                context_location["geocoder_reason"] = "context_location"
                context_location["area_match"] = True
                context_location["_from_text"] = False
                context_location["_from_context"] = True
                return _sanitize_location_result(original_text, context_location)

        return {
            "location_status": "unresolved",
            "location_candidates": [],
            "canonical_area": None,
            "location_confidence": 0.0,
            "location_source": "none",
            "matched_text": None,
            "needs_confirmation": False,
            "confirmation_type": "none",
            "debug": {
                "location_intent": location_intent,
                "remaining_text_for_location": slot_parse_context.get("remaining_text_for_location"),
            },
            "geocoder_called": False,
            "geocoder_reason": location_intent.get("reason") or "no_location_intent",
            "area_match": False,
            "_from_text": False,
            "_from_context": False,
        }

    fuzzy_location = resolve_location_fuzzy(str(location_text), supported_locations)
    legacy_location = resolve_location(normalize_text(str(location_text or "")), locale=locale)

    if legacy_location.get("location_status") in {"conflict", "multiple_choice"}:
        converted = _convert_legacy_location(legacy_location, supported_locations)
        converted["geocoder_reason"] = location_intent.get("reason") or "clear_area_match"
        return converted

    area_fallback = _extract_area_fallback(normalize_text(str(location_text or "")))
    if area_fallback:
        fallback_location = resolve_location_fuzzy(area_fallback, supported_locations)
        if fallback_location.get("location_status") == "ok":
            fallback_location["location_source"] = "district_fallback"
            fallback_location["_from_text"] = True
            fallback_location["_from_context"] = False
            return _sanitize_location_result(original_text, fallback_location)

    if (
        context_area
        and fuzzy_location.get("location_source") == "fuzzy_gazetteer"
        and float(fuzzy_location.get("location_confidence") or 0.0) < 0.9
    ):
        context_location = resolve_location_fuzzy(str(context_area), supported_locations)
        if context_location.get("location_status") == "ok":
            context_location["location_source"] = "context"
            context_location["location_confidence"] = 1.0
            context_location["_from_text"] = False
            context_location["_from_context"] = True
            return _sanitize_location_result(original_text, context_location)

    if (
        legacy_location.get("location_status") == "ok"
        and fuzzy_location.get("location_status") == "ok"
        and fuzzy_location.get("location_source") == "fuzzy_gazetteer"
    ):
        converted = _convert_legacy_location(legacy_location, supported_locations)
        converted["_from_text"] = True
        converted["_from_context"] = False
        return _sanitize_location_result(original_text, converted)

    if legacy_location.get("location_status") == "ok" and fuzzy_location.get("location_status") in {
        "unresolved",
        "ambiguous",
    }:
        converted = _convert_legacy_location(legacy_location, supported_locations)
        converted["_from_text"] = True
        converted["_from_context"] = False
        return _sanitize_location_result(original_text, converted)

    if fuzzy_location.get("location_status") != "unresolved":
        fuzzy_location["_from_text"] = True
        fuzzy_location["_from_context"] = False
        return _sanitize_location_result(original_text, fuzzy_location)

    if (
        legacy_location.get("location_status") == "unsupported"
        and fuzzy_location.get("location_source") == "fuzzy_gazetteer"
    ):
        return _convert_legacy_location(legacy_location, supported_locations)

    if legacy_location.get("location_status") == "ok":
        converted = _convert_legacy_location(legacy_location, supported_locations)
        converted["_from_text"] = True
        converted["_from_context"] = False
        return converted

    if USE_NER_FALLBACK:
        try:
            from .nlu_ner import extract_area_by_ner

            ner_area = extract_area_by_ner(text)
            if ner_area:
                ner_location = resolve_location_fuzzy(ner_area, supported_locations)
                if ner_location.get("location_status") == "ok":
                    ner_location["location_source"] = "ner_fallback"
                    ner_location["_from_text"] = True
                    ner_location["_from_context"] = False
                    return _sanitize_location_result(original_text, ner_location)
        except Exception:
            logger.debug("chat_api NER fallback failed", exc_info=True)

    if context_area:
        context_location = resolve_location_fuzzy(str(context_area), supported_locations)
        if context_location.get("location_status") == "ok":
            context_location["location_source"] = "context"
            context_location["location_confidence"] = 1.0
            context_location["_from_text"] = False
            context_location["_from_context"] = True
            return _sanitize_location_result(original_text, context_location)

    if legacy_location.get("location_status") == "unsupported":
        return _convert_legacy_location(legacy_location, supported_locations)

    fuzzy_location["_from_text"] = False
    fuzzy_location["_from_context"] = False
    return fuzzy_location


def _sanitize_location_result(text: str, location: dict[str, Any]) -> dict[str, Any]:
    if should_ignore_numeric_location_match(text, location.get("canonical_area")):
        return {
            "location_status": "unresolved",
            "location_candidates": [],
            "canonical_area": None,
            "location_confidence": 0.0,
            "location_source": "numeric_guest_guard",
            "matched_text": location.get("matched_text"),
            "needs_confirmation": False,
            "confirmation_type": "none",
            "debug": {
                "ignored_location": location.get("canonical_area"),
                "reason": "number_in_guest_count_context",
            },
            "_from_text": False,
            "_from_context": False,
        }
    return location


def _convert_legacy_location(legacy_location: dict[str, Any], supported_locations: list[dict]) -> dict[str, Any]:
    status = legacy_location.get("location_status") or "unresolved"
    canonical_area = legacy_location.get("canonical_area")
    if canonical_area:
        rematched = resolve_location_fuzzy(str(canonical_area), supported_locations)
        if rematched.get("location_status") == "ok":
            canonical_area = rematched.get("canonical_area")

    candidates = []
    for candidate in legacy_location.get("location_candidates") or []:
        name = candidate.get("canonical_area")
        if name:
            rematched = resolve_location_fuzzy(str(name), supported_locations)
            if rematched.get("location_status") == "ok":
                name = rematched.get("canonical_area")
        candidates.append({**candidate, "canonical_area": name})

    return {
        "location_status": status,
        "canonical_area": canonical_area if status == "ok" else None,
        "location_confidence": 0.9 if status == "ok" else 0.0,
        "location_source": "legacy_location_resolver" if status != "unresolved" else "none",
        "needs_confirmation": status in {"conflict", "multiple_choice"},
        "confirmation_type": "explicit" if status in {"conflict", "multiple_choice"} else "none",
        "location_candidates": candidates,
        "matched_text": None,
        "debug": legacy_location.get("debug", {}),
        "_from_text": status == "ok",
        "_from_context": False,
    }


def _finalize_convenience_response(
    result: dict[str, Any],
    text: str,
    *,
    router: dict[str, Any] | None = None,
    normalized: dict[str, Any] | None = None,
    llm_called: bool | None = None,
) -> dict[str, Any]:
    if router is None:
        router = classify_message(text, context_slots=None)
    if normalized is None:
        normalized = normalize_user_text(text)

    result["conversation_intent"] = result.get("conversation_intent") or router.get("intent") or result.get("intent")
    result.setdefault("raw_text", normalized["raw_text"])
    result.setdefault("location_confidence", 0.0)
    result.setdefault("location_source", "none")
    result.setdefault("matched_text", None)
    result.setdefault("assumptions", [])
    result.setdefault("used_default_slots", {})
    if llm_called is not None:
        result["llm_called"] = llm_called
    else:
        result.setdefault("llm_called", False)

    _attach_filter_tree_payload(result, text)
    policy = decide_user_effort_policy(result)
    result.update(policy)
    result["ready_for_recommendation"] = policy["can_show_recommendations"]
    result["confirmation_required"] = policy["needs_confirmation"]
    result["awaiting_confirmation"] = policy["needs_confirmation"]
    result["follow_up_question"] = policy["next_best_question"]
    result["suggested_questions"] = [policy["next_best_question"]] if policy["next_best_question"] else []
    result["polite_bot_message"] = _build_polite_message(result, policy)
    result["bot_message"] = result["polite_bot_message"]
    _attach_api_contract_metadata(result, policy)
    if result.get("can_show_recommendations"):
        add_confirmation_payload(result, require_confirmation=False)

    logger.info(
        "chat_api parse pipeline",
        extra={
            "chat_api_parse": {
                "raw_text": normalized["raw_text"][:160],
                "normalized_text": normalized["normalized_text"][:160],
                "router_intent": router.get("intent"),
                "router_confidence": router.get("confidence"),
                "location_source": result.get("location_source"),
                "location_confidence": result.get("location_confidence"),
                "recommendation_level": result.get("recommendation_level"),
                "llm_called": result.get("llm_called"),
                "can_show_recommendations": result.get("can_show_recommendations"),
                "policy_reason": _policy_reason(result),
            }
        },
    )
    return result


def _build_polite_message(result: dict[str, Any], policy: dict[str, Any]) -> str:
    return ResponseGenerator(
        terminal_intents=TERMINAL_INTENTS,
        message_slots_with_location=_message_slots_with_location,
        format_vnd=_format_vnd,
    ).generate(result, policy)


def _attach_api_contract_metadata(result: dict[str, Any], policy: dict[str, Any]) -> None:
    debug_metadata = result.get("debug_metadata") or {}
    result.setdefault("protected_spans", debug_metadata.get("protected_spans") or [])
    search_origin = build_search_origin(result)
    result["search_origin"] = search_origin
    result["slot_confidence"] = _slot_confidence_payload(result)
    result["location_meta"] = {
        "status": result.get("location_status"),
        "mode": result.get("location_mode"),
        "origin_type": search_origin["type"],
        "search_origin": search_origin,
        "source": result.get("location_source"),
        "phrase": result.get("location_phrase") or result.get("matched_text"),
        "confidence": result.get("location_confidence") or 0.0,
        "geocoder_called": bool(result.get("geocoder_called")),
        "geocoder_reason": result.get("geocoder_reason"),
        "location_source": result.get("location_source"),
        "cache_hit": bool(result.get("cache_hit")),
        "rejected_reason": result.get("rejected_reason"),
        "canonical_area": result.get("canonical_area"),
        "display_label": result.get("location_display_label"),
        "search_radius_km": result.get("search_radius_km"),
        "anchor": {
            "name": result.get("anchor_name"),
            "kind": result.get("anchor_kind"),
            "lat": result.get("anchor_lat"),
            "lon": result.get("anchor_lon"),
            "radius_km": result.get("anchor_radius_km"),
        },
        "map": {
            "area": result.get("map_area"),
            "display_name": result.get("map_display_name"),
            "address": result.get("map_address") or {},
        },
        "rejected_geocoder_results": result.get("rejected_geocoder_results") or [],
    }
    result["clarification"] = build_clarification_payload(result, policy)


def _slot_confidence_payload(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    slots = result.get("slots") or {}
    protected_spans = result.get("protected_spans") or []
    payload: dict[str, dict[str, Any]] = {}

    def add(name: str, value: Any, confidence: float, source: str) -> None:
        if value in (None, "", [], {}):
            return
        payload[name] = {
            "value": value,
            "confidence": round(float(confidence), 3),
            "source": source,
            "status": _confidence_status(confidence),
        }

    span_types = {span.get("type") for span in protected_spans if isinstance(span, dict)}
    type_source = "deterministic_fuzzy" if "accommodation_type" in span_types else "deterministic"
    amenity_source = "deterministic" if "amenity" in span_types else "deterministic"

    add("accommodation_types", slots.get("accommodation_types"), 0.95, type_source)
    add("amenities", slots.get("required_amenities"), 0.92, amenity_source)
    add("budget_min", slots.get("budget_min"), 0.95, "deterministic")
    add("budget_max", slots.get("budget_max") or slots.get("budget"), 0.95, "deterministic")
    add("guest_count", slots.get("guest_count"), 0.95, "deterministic")
    add("sort", slots.get("priorities"), 0.8, "deterministic")

    location_value = result.get("location_phrase") or result.get("canonical_area") or result.get("location_display_label")
    if location_value:
        confidence = float(result.get("location_confidence") or 0.0)
        add("location", location_value, confidence, result.get("location_source") or "deterministic")
    return payload


def _confidence_status(confidence: float) -> str:
    if confidence >= 0.80:
        return "accepted"
    if confidence >= 0.55:
        return "needs_confirmation"
    return "ignored"


def _build_city_center_message(result: dict[str, Any], policy: dict[str, Any]) -> str:
    slots = result.get("slots") or {}
    label = result.get("location_display_label") or result.get("anchor_name") or "trung tâm thành phố"
    parts = [f"Được nhé, mình sẽ tìm các chỗ ở gần {label}"]
    guest_count = slots.get("guest_count")
    budget_max = slots.get("budget_max") or slots.get("budget")
    if guest_count:
        parts.append(f"cho {guest_count} người")
    if budget_max:
        parts.append(f"ngân sách dưới {_format_vnd(budget_max)}/đêm")
    message = ", ".join(parts) + "."
    if policy.get("recommendation_level") == "partial" and policy.get("next_best_question"):
        message = f"{message} {policy['next_best_question']}"
    return message


def _policy_reason(result: dict[str, Any]) -> str:
    if result.get("can_show_recommendations"):
        return "usable_filter_tree"
    if result.get("conversation_intent") in TERMINAL_INTENTS:
        return f"terminal_intent:{result.get('conversation_intent')}"
    return f"location_status:{result.get('location_status')}"


def _hf_agent_enabled() -> bool:
    value = os.getenv("CHAT_API_ENABLE_HF_AGENT", "0").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _llm_strategy() -> str:
    if not _hf_agent_enabled():
        return "never"

    value = os.getenv("CHAT_API_LLM_STRATEGY", "auto").strip().lower()
    if value not in {"auto", "always", "never"}:
        return "auto"
    return value


def _can_answer_fast(result: dict[str, Any]) -> bool:
    if result.get("conversation_intent") in TERMINAL_INTENTS:
        return True
    if result.get("can_show_recommendations"):
        return True
    if result.get("location_status") in {"multiple_choice", "conflict"}:
        return True
    if result.get("location_status") == "unresolved" and not has_recommendation_signal(result.get("slots")):
        return True

    slots = result.get("slots") or {}
    useful_slots = [
        slots.get("area"),
        slots.get("budget_min") or slots.get("budget_max") or slots.get("budget"),
        slots.get("guest_count"),
        slots.get("preferred_type"),
        slots.get("accommodation_type"),
        slots.get("accommodation_types"),
        slots.get("required_amenities"),
        slots.get("priorities"),
        slots.get("special_requirements"),
        slots.get("room_count"),
        slots.get("rating"),
    ]
    filter_tree = result.get("filter_tree") or {}
    return bool(
        any(useful_slots)
        or result.get("location_mode") in {"area", "near_anchor", "near_user", "anywhere"}
        or filter_tree.get("usable_filter_count", 0) > 0
    )


def _finalize_parse_result(
    result: dict[str, Any],
    text: str,
    *,
    locale: str,
    context_slots: dict[str, Any] | None,
    include_debug: bool | None = None,
) -> dict[str, Any]:
    router = classify_message(text, context_slots=context_slots, locale=locale)
    normalized = normalize_user_text(text)
    slot_parse_context = build_slot_parse_context(text)
    slots = validate_slots(merge_slot_context(result.get("slots") or {}, context_slots))
    result["slots"] = slots
    result["missing_slots"] = core_missing_slots(slots)
    result["protected_spans"] = public_protected_spans(slot_parse_context)

    if not result.get("location_confidence"):
        location = _resolve_location_pipeline(
            text,
            locale=locale,
            context_slots=context_slots,
            slot_parse_context=slot_parse_context,
        )
        if location.get("location_status") == "ok":
            result["location_status"] = "ok"
            result["canonical_area"] = location.get("canonical_area")
            result["slots"]["area"] = location.get("canonical_area")
        else:
            result.setdefault("location_status", location.get("location_status", "unresolved"))
            result.setdefault("canonical_area", location.get("canonical_area"))
        result["location_candidates"] = location.get("location_candidates", result.get("location_candidates", []))
        result["location_confidence"] = location.get("location_confidence", 0.0)
        result["location_source"] = location.get("location_source", "none")
        result["matched_text"] = location.get("matched_text")
        if _include_debug_metadata(include_debug):
            _attach_parse_debug_metadata(result, slot_parse_context=slot_parse_context, location=location)
    elif _include_debug_metadata(include_debug) and not result.get("debug_metadata"):
        _attach_parse_debug_metadata(result, slot_parse_context=slot_parse_context)

    result["conversation_intent"] = router["intent"]
    return _finalize_convenience_response(result, text, router=router, normalized=normalized, llm_called=result.get("llm_called"))


def parse_user_text(
    text: str,
    *,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
    include_debug: bool | None = None,
) -> dict[str, Any]:
    """Public parser entrypoint kept backward-compatible for existing callers."""

    fallback_result = parse_user_text_rule_based(
        text,
        locale=locale,
        context_slots=context_slots,
        include_debug=include_debug,
    )
    fast_result = fallback_result

    strategy = _llm_strategy()
    if strategy == "never":
        return fast_result
    if strategy == "auto" and _can_answer_fast(fast_result):
        return fast_result

    try:
        from .agent.llm_parser import get_hf_slot_parser

        result = get_hf_slot_parser().parse(
            text,
            locale=locale,
            context_slots=context_slots,
            fallback_result=fallback_result,
        )
        result["llm_called"] = True
        return _finalize_parse_result(
            result,
            text,
            locale=locale,
            context_slots=context_slots,
            include_debug=include_debug,
        )
    except Exception:
        logger.exception("chat_api hf parser failed before fallback")

        fallback_result["llm_called"] = True
        return fallback_result
