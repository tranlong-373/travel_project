from __future__ import annotations

import logging
import os
import re
from typing import Any

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
from .normalizers import normalize_text
from .questions import build_suggested_questions
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .validators import validate_and_normalize_slots

USE_NER_FALLBACK = os.getenv("CHAT_API_USE_NER", "0") == "1"
INCLUDE_PARSE_DIAGNOSTICS = os.getenv("CHAT_API_INCLUDE_DIAGNOSTICS", "0") == "1"
logger = logging.getLogger(__name__)


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

    for k in ["area", "budget", "guest_count", "preferred_type", "trip_days"]:
        v = slots_new.get(k)
        if v is not None:
            merged[k] = v

    for k in ["required_amenities", "priorities", "special_requirements"]:
        base = merged.get(k) or []
        add = slots_new.get(k) or []
        merged[k] = list(dict.fromkeys(list(base) + list(add)))

    return merged


def parse_user_text(text: str, *, locale: str = "vi", context_slots: dict[str, Any] | None = None) -> dict[str, Any]:
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

    return response