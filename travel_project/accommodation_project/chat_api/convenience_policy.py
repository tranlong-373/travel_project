from __future__ import annotations

from typing import Any

TERMINAL_INTENTS = {"off_topic", "unknown", "greeting", "thanks", "help", "goodbye"}


def decide_user_effort_policy(parse_result: dict) -> dict:
    intent = parse_result.get("conversation_intent") or parse_result.get("intent")
    slots = parse_result.get("slots") or {}
    location_status = parse_result.get("location_status") or "unresolved"
    canonical_area = parse_result.get("canonical_area") or slots.get("area")
    confidence = float(parse_result.get("location_confidence") or 0.0)

    base = {
        "recommendation_level": "none",
        "can_show_recommendations": False,
        "needs_user_action": False,
        "needs_confirmation": False,
        "confirmation_type": "none",
        "next_best_question": None,
        "quick_replies": [],
        "assumptions": list(parse_result.get("assumptions") or []),
    }

    if intent in TERMINAL_INTENTS:
        base["next_best_question"] = None
        return base

    if location_status == "multiple_choice":
        base.update(
            {
                "needs_user_action": True,
                "needs_confirmation": True,
                "confirmation_type": "explicit",
                "next_best_question": "Bạn muốn chọn khu vực nào?",
            }
        )
        base["quick_replies"] = _location_quick_replies(parse_result.get("location_candidates") or [])
        return base

    if location_status == "conflict":
        base.update(
            {
                "needs_user_action": True,
                "needs_confirmation": True,
                "confirmation_type": "explicit",
                "next_best_question": "Bạn xác nhận lại khu vực muốn tìm giúp mình nhé?",
            }
        )
        base["quick_replies"] = _location_quick_replies(parse_result.get("location_candidates") or [])
        return base

    if location_status == "ambiguous" or 0.60 <= confidence < 0.75:
        base.update(
            {
                "needs_user_action": True,
                "needs_confirmation": True,
                "confirmation_type": "explicit",
                "next_best_question": "Mình chưa chắc khu vực bạn muốn tìm, bạn xác nhận giúp mình nhé?",
            }
        )
        base["quick_replies"] = _location_quick_replies(parse_result.get("location_candidates") or [])
        return base

    if location_status in {"unsupported", "unresolved"} or not canonical_area:
        base.update(
            {
                "needs_user_action": True,
                "next_best_question": "Bạn muốn tìm chỗ ở khu vực nào?",
            }
        )
        base["quick_replies"] = _popular_location_replies()
        return base

    if location_status == "ok" and canonical_area:
        has_budget = bool(slots.get("budget") or slots.get("budget_max"))
        has_guest_count = bool(slots.get("guest_count"))
        full = bool(has_budget and has_guest_count)
        base["recommendation_level"] = "full" if full else "partial"
        base["can_show_recommendations"] = True
        base["needs_user_action"] = False
        if confidence >= 0.90:
            base["needs_confirmation"] = False
            base["confirmation_type"] = "none"
        elif 0.75 <= confidence < 0.90:
            base["needs_confirmation"] = False
            base["confirmation_type"] = "implicit"
            base["assumptions"].append(
                {
                    "slot": "area",
                    "value": canonical_area,
                    "confidence": confidence,
                    "reason": "fuzzy_location_implicit_match",
                }
            )
        else:
            base["needs_confirmation"] = False
            base["confirmation_type"] = "none"

        base["next_best_question"] = _next_best_question(slots)
        base["quick_replies"] = _quick_replies_for_missing(slots)
        return base

    return base


def _next_best_question(slots: dict[str, Any]) -> str | None:
    if not (slots.get("budget") or slots.get("budget_max")):
        return "Nếu muốn lọc sát hơn, bạn cho mình biết thêm khoảng ngân sách/đêm nhé."
    if not slots.get("guest_count"):
        return "Bạn đi mấy người để mình lọc phòng phù hợp hơn nhé?"
    if not slots.get("required_amenities") and not slots.get("priorities"):
        return "Bạn có ưu tiên nào như wifi, gần trung tâm hoặc yên tĩnh không?"
    return None


def _quick_replies_for_missing(slots: dict[str, Any]) -> list[dict]:
    replies: list[dict] = []
    if not (slots.get("budget") or slots.get("budget_max")):
        replies.extend(
            [
                {"label": "500k - 800k", "payload": {"budget_min": 500000, "budget_max": 800000}},
                {"label": "800k - 1tr2", "payload": {"budget_min": 800000, "budget_max": 1200000}},
                {"label": "1tr2+", "payload": {"budget_min": 1200000}},
            ]
        )
    if not slots.get("guest_count"):
        replies.extend(
            [
                {"label": "Đi 1 người", "payload": {"guest_count": 1}},
                {"label": "Đi 2 người", "payload": {"guest_count": 2}},
                {"label": "Gia đình", "payload": {"guest_count": 4}},
            ]
        )
    if not replies and not slots.get("required_amenities") and not slots.get("priorities"):
        replies.extend(
            [
                {"label": "Có wifi", "payload": {"required_amenities": ["wifi"]}},
                {"label": "Gần trung tâm", "payload": {"priorities": ["near_center"]}},
                {"label": "Yên tĩnh", "payload": {"priorities": ["quiet"]}},
            ]
        )
    return replies[:5]


def _location_quick_replies(candidates: list[dict]) -> list[dict]:
    replies = []
    for candidate in candidates[:5]:
        name = candidate.get("canonical_area")
        if name:
            replies.append({"label": name, "payload": {"area": name}})
    return replies


def _popular_location_replies() -> list[dict]:
    return [
        {"label": "TP HCM", "payload": {"area": "TP HCM"}},
        {"label": "Hà Nội", "payload": {"area": "Hà Nội"}},
        {"label": "Đà Lạt", "payload": {"area": "Đà Lạt"}},
    ]
