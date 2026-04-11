from __future__ import annotations

import re
from typing import Any

from .extractors import find_area_candidates, find_type_candidates, has_type_choice_connector
from .normalizers import normalize_key

TOTAL_BUDGET_CUES = (
    "tong",
    "total",
    "ca chuyen",
    "ca dot",
    "chi phi",
    "gia ca",
    "all in",
    "for the trip",
)

PER_NIGHT_BUDGET_CUES = (
    "/dem",
    "moi dem",
    "per night",
    "/night",
    "nightly",
)


def _question(locale: str, vi: str, en: str) -> str:
    return en if locale == "en" else vi


def _budget_needs_clarification(text: str, slots: dict[str, Any]) -> bool:
    if not slots.get("budget"):
        return False

    norm = normalize_key(text)
    if any(cue in norm for cue in PER_NIGHT_BUDGET_CUES):
        return False

    has_total_cue = any(cue in norm for cue in TOTAL_BUDGET_CUES)
    return bool(has_total_cue and (slots.get("trip_days") or 0) > 1)


def _drop_parent_area_candidates(candidates: list[str]) -> list[str]:
    has_specific_hcm_area = any(c != "tp hcm" and c.endswith("tp hcm") for c in candidates)
    if has_specific_hcm_area and "tp hcm" in candidates:
        return [c for c in candidates if c != "tp hcm"]
    return candidates


def _has_negated_priority_conflict(text: str, slots: dict[str, Any]) -> bool:
    priorities = slots.get("priorities") or []
    if "cheap" not in priorities:
        return False

    norm = normalize_key(text)
    return bool(
        re.search(
            r"\b(?:khong can|ko can|khong muon|ko muon|no need|dont need|don't need).{0,24}(?:re|cheap|affordable)\b",
            norm,
        )
    )


def evaluate_parse_gate(
    text: str,
    slots: dict[str, Any],
    *,
    locale: str = "vi",
    location_status: str | None = None,
) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    diagnostics: dict[str, Any] = {}
    follow_up_question: str | None = None

    if location_status is None:
        area_candidates = _drop_parent_area_candidates(find_area_candidates(text))
        if len(area_candidates) > 1:
            diagnostics["area_candidates"] = area_candidates

        if not slots.get("area") and len(area_candidates) > 1:
            blocking_reasons.append("ambiguous_area")
            choices = ", ".join(area_candidates)
            follow_up_question = _question(
                locale,
                f"Bạn muốn ở khu vực nào trong các lựa chọn này: {choices}?",
                f"Which area do you prefer: {choices}?",
            )

    type_candidates = find_type_candidates(text)
    if len(type_candidates) > 1:
        diagnostics["type_candidates"] = type_candidates
        diagnostics["type_choice_unresolved"] = has_type_choice_connector(text)

    if _budget_needs_clarification(text, slots):
        blocking_reasons.append("weak_budget")
        diagnostics["budget_clarification"] = "budget_may_be_total_trip_cost"
        if follow_up_question is None:
            follow_up_question = _question(
                locale,
                "Ngân sách đó là cho mỗi đêm hay cho cả chuyến?",
                "Is that budget per night or for the whole trip?",
            )

    if _has_negated_priority_conflict(text, slots):
        blocking_reasons.append("negated_priority_conflict")
        diagnostics["negated_priority_conflict"] = "cheap"
        if follow_up_question is None:
            follow_up_question = _question(
                locale,
                "Mình sẽ không xem 'rẻ' là ưu tiên. Bạn muốn ngân sách tối đa khoảng bao nhiêu VND/đêm?",
                "I will not treat cheap as a priority. What max budget per night should I use?",
            )

    return {
        "blocking_reasons": blocking_reasons,
        "diagnostics": diagnostics,
        "follow_up_question": follow_up_question,
        "safe_for_recommendation": not blocking_reasons,
    }
