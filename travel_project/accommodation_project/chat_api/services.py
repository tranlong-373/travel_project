from __future__ import annotations

import logging
import os
import re
from typing import Any

from .convenience_policy import TERMINAL_INTENTS, decide_user_effort_policy
from .constants import NUMBER_WORDS
from .domain_router import classify_message
from .extractors import (
    find_unsupported_type_candidates,
)
from .fuzzy_location import resolve_location_fuzzy
from .gate import evaluate_parse_gate
from .location_gazetteer import load_supported_locations
from .location_resolver import resolve_location
from .normalizers import normalize_key, normalize_text
from .questions import build_suggested_questions
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
    build_unsupported_message,
)
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .slot_validator import core_missing_slots, extract_slots_from_text, merge_slot_context, validate_slots
from .text_normalizer import normalize_user_text
from .validators import validate_and_normalize_slots

USE_NER_FALLBACK = os.getenv("CHAT_API_USE_NER", "0") == "1"
INCLUDE_PARSE_DIAGNOSTICS = os.getenv("CHAT_API_INCLUDE_DIAGNOSTICS", "0") == "1"
logger = logging.getLogger(__name__)

CONFIRM_CORE_KEYS = ("area", "guest_count", "budget", "trip_days")
CONFIRM_SKIP_KEYS = {"budget_min", "budget_max"}
RECOMMENDATION_SIGNAL_KEYS = (
    "area",
    "guest_count",
    "budget",
    "trip_days",
    "preferred_type",
    "required_amenities",
    "priorities",
    "special_requirements",
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
    "required_amenities": "Tiện nghi yêu cầu",
    "priorities": "Ưu tiên",
    "special_requirements": "Yêu cầu đặc biệt",
    "check_in": "Ngày nhận phòng",
    "check_out": "Ngày trả phòng",
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

    for k in ["area", "budget", "budget_min", "budget_max", "guest_count", "preferred_type", "trip_days"]:
        v = slots_new.get(k)
        if v is not None:
            merged[k] = v

    for k in ["required_amenities", "priorities", "special_requirements"]:
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
        return slots.get("budget") or slots.get("budget_max")
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
                "display_value": _display_confirm_value(value),
            })
            included.add(key)

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
) -> dict[str, Any]:
    normalized = normalize_user_text(text)
    raw = normalized["normalized_text"]
    router = classify_message(text, context_slots=context_slots, locale=locale)

    if router["intent"] in TERMINAL_INTENTS:
        response = _terminal_response(router, normalized, context_slots=context_slots)
        return _finalize_convenience_response(response, text, router=router, normalized=normalized)

    location = _resolve_location_pipeline(
        text,
        locale=locale,
        context_slots=context_slots,
        prefer_context=router["intent"] == "clarify_slot",
    )
    slots_partial = extract_slots_from_text(text, canonical_area=location.get("canonical_area"))
    _apply_bare_count_follow_up(slots_partial, raw, context_slots)

    replace_area = bool(location.get("_from_text") and location.get("location_status") == "ok")
    slots_partial = merge_slot_context(slots_partial, context_slots, replace_area=replace_area)
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
    }

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


def _resolve_location_pipeline(
    text: str,
    *,
    locale: str,
    context_slots: dict[str, Any] | None,
    prefer_context: bool = False,
) -> dict[str, Any]:
    supported_locations = load_supported_locations()
    fuzzy_location = resolve_location_fuzzy(text, supported_locations)
    legacy_location = resolve_location(normalize_text(text or ""), locale=locale)
    context_area = (context_slots or {}).get("area") or (context_slots or {}).get("canonical_area")

    if prefer_context and context_area:
        context_location = resolve_location_fuzzy(str(context_area), supported_locations)
        if context_location.get("location_status") == "ok":
            context_location["location_source"] = "context"
            context_location["location_confidence"] = 1.0
            context_location["_from_text"] = False
            context_location["_from_context"] = True
            return context_location

    if legacy_location.get("location_status") in {"conflict", "multiple_choice"}:
        return _convert_legacy_location(legacy_location, supported_locations)

    area_fallback = _extract_area_fallback(normalize_text(text or ""))
    if area_fallback:
        fallback_location = resolve_location_fuzzy(area_fallback, supported_locations)
        if fallback_location.get("location_status") == "ok":
            fallback_location["location_source"] = "district_fallback"
            fallback_location["_from_text"] = True
            fallback_location["_from_context"] = False
            return fallback_location

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
            return context_location

    if (
        legacy_location.get("location_status") == "ok"
        and fuzzy_location.get("location_status") == "ok"
        and fuzzy_location.get("location_source") == "fuzzy_gazetteer"
    ):
        converted = _convert_legacy_location(legacy_location, supported_locations)
        converted["_from_text"] = True
        converted["_from_context"] = False
        return converted

    if legacy_location.get("location_status") == "ok" and fuzzy_location.get("location_status") in {
        "unresolved",
        "ambiguous",
    }:
        converted = _convert_legacy_location(legacy_location, supported_locations)
        converted["_from_text"] = True
        converted["_from_context"] = False
        return converted

    if fuzzy_location.get("location_status") != "unresolved":
        fuzzy_location["_from_text"] = True
        fuzzy_location["_from_context"] = False
        return fuzzy_location

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
                    return ner_location
        except Exception:
            logger.debug("chat_api NER fallback failed", exc_info=True)

    if context_area:
        context_location = resolve_location_fuzzy(str(context_area), supported_locations)
        if context_location.get("location_status") == "ok":
            context_location["location_source"] = "context"
            context_location["location_confidence"] = 1.0
            context_location["_from_text"] = False
            context_location["_from_context"] = True
            return context_location

    if legacy_location.get("location_status") == "unsupported":
        return _convert_legacy_location(legacy_location, supported_locations)

    fuzzy_location["_from_text"] = False
    fuzzy_location["_from_context"] = False
    return fuzzy_location


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
    result.setdefault("location_confidence", 0.0)
    result.setdefault("location_source", "none")
    result.setdefault("matched_text", None)
    result.setdefault("assumptions", [])
    result.setdefault("used_default_slots", {})
    if llm_called is not None:
        result["llm_called"] = llm_called
    else:
        result.setdefault("llm_called", False)

    policy = decide_user_effort_policy(result)
    result.update(policy)
    result["ready_for_recommendation"] = policy["can_show_recommendations"]
    result["confirmation_required"] = policy["needs_confirmation"]
    result["awaiting_confirmation"] = policy["needs_confirmation"]
    result["follow_up_question"] = policy["next_best_question"]
    result["suggested_questions"] = [policy["next_best_question"]] if policy["next_best_question"] else []
    result["polite_bot_message"] = _build_polite_message(result, policy)
    result["bot_message"] = result["polite_bot_message"]
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
    intent = result.get("conversation_intent") or result.get("intent")
    status = result.get("location_status")

    if intent == "off_topic":
        return build_off_topic_message()
    if intent == "unknown":
        return build_unknown_message()
    if intent == "greeting":
        return build_greeting_message()
    if intent == "thanks":
        return build_thanks_message()
    if intent == "goodbye":
        return build_goodbye_message()
    if intent == "help":
        return build_help_message()
    if status == "multiple_choice":
        return build_multiple_choice_message(result.get("location_candidates") or [])
    if status == "conflict":
        return build_conflict_message(result)
    if status == "unsupported":
        return build_unsupported_message()
    if status == "unresolved":
        return build_unresolved_location_message()
    if status == "ambiguous":
        return build_explicit_confirmation_message(result.get("location_candidates") or [])
    if policy.get("confirmation_type") == "implicit" and policy.get("assumptions"):
        return build_implicit_confirmation_message(policy["assumptions"][0])
    if policy.get("recommendation_level") == "full":
        return build_full_message(result.get("slots") or {})
    if policy.get("recommendation_level") == "partial":
        return build_partial_message(
            result.get("slots") or {},
            assumptions=policy.get("assumptions"),
            next_best_question=policy.get("next_best_question"),
        )
    return build_unknown_message()


def _policy_reason(result: dict[str, Any]) -> str:
    if result.get("can_show_recommendations"):
        return "valid_location"
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
        slots.get("budget_max") or slots.get("budget"),
        slots.get("guest_count"),
        slots.get("preferred_type"),
        slots.get("required_amenities"),
        slots.get("priorities"),
        slots.get("special_requirements"),
    ]
    return bool(any(useful_slots) and result.get("follow_up_question"))


def _finalize_parse_result(
    result: dict[str, Any],
    text: str,
    *,
    locale: str,
    context_slots: dict[str, Any] | None,
) -> dict[str, Any]:
    router = classify_message(text, context_slots=context_slots, locale=locale)
    normalized = normalize_user_text(text)
    slots = validate_slots(merge_slot_context(result.get("slots") or {}, context_slots))
    result["slots"] = slots
    result["missing_slots"] = core_missing_slots(slots)

    if not result.get("location_confidence"):
        location = _resolve_location_pipeline(text, locale=locale, context_slots=context_slots)
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

    result["conversation_intent"] = router["intent"]
    return _finalize_convenience_response(result, text, router=router, normalized=normalized, llm_called=result.get("llm_called"))


def parse_user_text(text: str, *, locale: str = "vi", context_slots: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public parser entrypoint kept backward-compatible for existing callers."""

    fallback_result = parse_user_text_rule_based(text, locale=locale, context_slots=context_slots)
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
        return _finalize_parse_result(result, text, locale=locale, context_slots=context_slots)
    except Exception:
        logger.exception("chat_api hf parser failed before fallback")

        fallback_result["llm_called"] = True
        return fallback_result
