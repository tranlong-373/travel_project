from __future__ import annotations

import logging
import os
import re
from typing import Any

from .constants import NUMBER_WORDS
from .extractors import (
    extract_budget,
    find_unsupported_type_candidates,
    extract_guest_count,
    extract_preferred_type,
    extract_priorities,
    extract_required_amenities,
    extract_special_requirements,
    extract_trip_days,
)
from .gate import evaluate_parse_gate
from .location_resolver import resolve_location
from .normalizers import normalize_key, normalize_text
from .questions import build_suggested_questions
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .validators import validate_and_normalize_slots

USE_NER_FALLBACK = os.getenv("CHAT_API_USE_NER", "0") == "1"
INCLUDE_PARSE_DIAGNOSTICS = os.getenv("CHAT_API_INCLUDE_DIAGNOSTICS", "0") == "1"
logger = logging.getLogger(__name__)

CONFIRM_CORE_KEYS = ("area", "guest_count", "budget", "trip_days")
CONFIRM_SKIP_KEYS = {"budget_min", "budget_max"}
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


def _extract_area_fallback(text: str) -> str | None:
    text_lower = text.lower().strip()

    # Bắt các kiểu: quận 1, quan 1, q1, q.1, q 1, district 1
    match = re.search(r"\b(?:quận|quan|q\.?|district)\s*(\d+)\b", text_lower)
    if match:
        return f"Quận {match.group(1)}"

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

    if "quận 7" in text_lower or "quan 7" in text_lower:
        return "Quận 7"

    if "quận 1" in text_lower or "quan 1" in text_lower:
        return "Quận 1"

    return None


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


def build_confirm_table(slots: dict[str, Any]) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    included: set[str] = set()

    for key in CONFIRM_CORE_KEYS:
        value = _confirm_value(slots, key)
        if _has_confirm_value(value):
            table.append({"key": key, "label": _confirm_label(key), "value": value})
            included.add(key)

    for key, value in (slots or {}).items():
        if key in included or key in CONFIRM_SKIP_KEYS:
            continue
        if _has_confirm_value(value):
            table.append({"key": key, "label": _confirm_label(key), "value": value})

    return table


def add_confirmation_payload(result: dict[str, Any], *, locale: str = "vi") -> dict[str, Any]:
    result["awaiting_confirmation"] = False
    result["confirmation_required"] = False

    if result.get("ready_for_recommendation") and not result.get("missing_slots"):
        result["awaiting_confirmation"] = True
        result["confirmation_required"] = True
        result["confirm_table"] = build_confirm_table(result.get("slots") or {})
        result["confirmation_options"] = [
            {"id": "confirm", "label": "Xác nhận thông tin"},
            {"id": "add_more", "label": "Tôi còn yêu cầu thêm"},
        ]
        if locale == "en":
            result["follow_up_question"] = (
                "Please review the information below. Do you want to confirm or add more requirements?"
            )
        else:
            result["follow_up_question"] = (
                "Bạn vui lòng kiểm tra lại thông tin bên dưới. Bạn muốn xác nhận hay thêm yêu cầu khác?"
            )

    return result


def parse_user_text_rule_based(
    text: str,
    *,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = normalize_text(text)
    location = resolve_location(raw, locale=locale)

    # Fallback nếu location_resolver chưa nhận ra khu vực
    if location["location_status"] != "ok":
        area_fallback = _extract_area_fallback(raw)
        if area_fallback:
            fallback_location = resolve_location(area_fallback, locale=locale)
            if fallback_location["location_status"] == "ok":
                location = fallback_location
            else:
                location = {
                    **location,
                    "location_status": "ok",
                    "canonical_area": area_fallback,
                    "follow_up_question": None,
                }

    unsupported_type_candidates = find_unsupported_type_candidates(raw)

    slots_partial = {
        "area": location["canonical_area"] if location["location_status"] == "ok" else None,
        "budget": extract_budget(raw),
        "guest_count": extract_guest_count(raw),
        "preferred_type": extract_preferred_type(raw),
        "required_amenities": extract_required_amenities(raw),
        "priorities": extract_priorities(raw),
        "special_requirements": extract_special_requirements(raw),
        "trip_days": extract_trip_days(raw),
    }
    _apply_bare_count_follow_up(slots_partial, raw, context_slots)

    # NER chỉ là fallback tùy chọn, mặc định tắt để ưu tiên tốc độ
    if USE_NER_FALLBACK and location["location_status"] == "unresolved":
        try:
            from .nlu_ner import extract_area_by_ner

            ner_area = extract_area_by_ner(text)
            if ner_area:
                ner_location = resolve_location(ner_area, locale=locale)
                if ner_location["location_status"] == "ok":
                    location = ner_location
                    slots_partial["area"] = ner_location["canonical_area"]
        except Exception:
            pass

    context_for_merge = context_slots
    if context_slots and location["location_status"] != "unresolved":
        context_for_merge = dict(context_slots)
        context_for_merge.pop("area", None)

    slots_partial = merge_context(slots_partial, context_for_merge)
    slots = validate_and_normalize_slots(slots_partial)

    if location["location_status"] == "unresolved" and slots.get("area"):
        context_location = resolve_location(str(slots["area"]), locale=locale)
        if context_location["location_status"] == "ok":
            location = context_location
            slots["area"] = context_location["canonical_area"]

    if location["location_status"] != "ok":
        slots["area"] = None

    missing_slots = [k for k in CORE_SLOTS if not slots.get(k)]
    gate = evaluate_parse_gate(raw, slots, locale=locale, location_status=location["location_status"])
    ready_for_recommendation = (
        len(missing_slots) == 0
        and gate["safe_for_recommendation"]
        and location["location_status"] == "ok"
    )

    should_ask_optional = (
        ready_for_recommendation
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

    if location.get("follow_up_question"):
        suggested_questions = [location["follow_up_question"]]
    elif gate.get("follow_up_question"):
        suggested_questions = [gate["follow_up_question"]]

    if gate["blocking_reasons"]:
        logger.info(
            "chat_api parse gate blocked recommendation",
            extra={
                "chat_api_parse_gate": {
                    "reasons": gate["blocking_reasons"],
                    "missing_slots": missing_slots,
                    "text_length": len(raw),
                }
            },
        )

    response = {
        "schema_version": SCHEMA_VERSION,
        "intent": INTENT_DEFAULT,
        "slots": slots,
        "missing_slots": missing_slots,
        "suggested_questions": suggested_questions,
        "ready_for_recommendation": ready_for_recommendation,
        "should_ask_optional": should_ask_optional,
        "follow_up_question": suggested_questions[0] if suggested_questions else None,
        "parser_mode": "deterministic_fast",
        "location_status": location["location_status"],
        "location_candidates": location.get("location_candidates", []),
        "canonical_area": location.get("canonical_area"),
    }

    if INCLUDE_PARSE_DIAGNOSTICS:
        response["diagnostics"] = {
            "blocking_reasons": gate["blocking_reasons"],
            **gate["diagnostics"],
            "location": location.get("debug", {}),
        }
        if unsupported_type_candidates:
            response["diagnostics"]["unsupported_type_candidates"] = unsupported_type_candidates

    return add_confirmation_payload(response, locale=locale)


def _hf_agent_enabled() -> bool:
    value = os.getenv("CHAT_API_ENABLE_HF_AGENT", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _llm_strategy() -> str:
    if not _hf_agent_enabled():
        return "never"

    value = os.getenv("CHAT_API_LLM_STRATEGY", "auto").strip().lower()
    if value not in {"auto", "always", "never"}:
        return "auto"
    return value


def _can_answer_fast(result: dict[str, Any]) -> bool:
    if result.get("ready_for_recommendation"):
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


def parse_user_text(text: str, *, locale: str = "vi", context_slots: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public parser entrypoint kept backward-compatible for existing callers."""

    fallback_result = parse_user_text_rule_based(text, locale=locale, context_slots=context_slots)
    from .agent.parser_fallback import normalize_rule_result

    fast_result = normalize_rule_result(
        text,
        locale=locale,
        context_slots=context_slots,
        fallback_result=fallback_result,
        parser_mode="hybrid_rule_fast",
    )

    strategy = _llm_strategy()
    if strategy == "never":
        return add_confirmation_payload(fast_result, locale=locale)
    if strategy == "auto" and _can_answer_fast(fast_result):
        return add_confirmation_payload(fast_result, locale=locale)

    try:
        from .agent.llm_parser import get_hf_slot_parser

        result = get_hf_slot_parser().parse(
            text,
            locale=locale,
            context_slots=context_slots,
            fallback_result=fallback_result,
        )
        return add_confirmation_payload(result, locale=locale)
    except Exception:
        logger.exception("chat_api hf parser failed before fallback")

        result = normalize_rule_result(
            text,
            locale=locale,
            context_slots=context_slots,
            fallback_result=fallback_result,
        )
        return add_confirmation_payload(result, locale=locale)
