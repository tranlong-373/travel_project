from __future__ import annotations

from typing import Any

TERMINAL_INTENTS = {"off_topic", "unknown", "greeting", "thanks", "help", "goodbye"}
NON_LOCATION_FILTER_KEYS = (
    "preferred_type",
    "accommodation_type",
    "accommodation_types",
    "required_amenities",
    "amenities",
    "budget",
    "budget_min",
    "budget_max",
    "guest_count",
    "room_count",
    "rating",
    "priorities",
    "special_requirements",
    "checkin_date",
    "checkout_date",
    "check_in",
    "check_out",
)
LOCATION_REFINEMENT_QUESTION = "Bạn muốn tìm quanh khu vực hoặc địa danh nào để mình lọc sát hơn không?"


def decide_user_effort_policy(parse_result: dict) -> dict:
    intent = parse_result.get("conversation_intent") or parse_result.get("intent")
    slots = parse_result.get("slots") or {}
    location_status = parse_result.get("location_status") or "unresolved"
    canonical_area = parse_result.get("canonical_area") or slots.get("area")
    confidence = float(parse_result.get("location_confidence") or 0.0)
    location_mode = parse_result.get("location_mode") or (parse_result.get("filter_tree") or {}).get("location", {}).get("mode")
    usable_filter_count = int((parse_result.get("filter_tree") or {}).get("usable_filter_count") or 0)
    has_usable_filters = usable_filter_count > 0 or _has_usable_slot(slots)
    has_resolved_location_filter = usable_filter_count > 0 and (
        location_mode in {"area", "near_anchor", "near_user", "city_center", "anywhere"} or bool(canonical_area)
    )
    has_non_location_filter = _has_non_location_filter(parse_result, slots)

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

    if intent in TERMINAL_INTENTS and not (
        intent == "unknown" and (has_usable_filters or parse_result.get("ambiguous_location"))
    ):
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

    if location_mode == "multiple_choice":
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

    if location_mode == "conflict":
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

    if location_status == "unsupported" or location_mode == "unsupported":
        base.update(
            {
                "needs_user_action": True,
                "next_best_question": "Khu vực này hiện mình chưa chắc có dữ liệu. Bạn cho mình thêm ngân sách, số người hoặc chọn khu vực khác nhé?",
            }
        )
        base["quick_replies"] = _popular_location_replies()
        return base

    if parse_result.get("unresolved_location") and has_non_location_filter:
        base.update(
            {
                "recommendation_level": "partial",
                "can_show_recommendations": True,
                "needs_user_action": False,
                "missing_slots": ["location"],
                "next_best_question": LOCATION_REFINEMENT_QUESTION,
            }
        )
        return base

    if parse_result.get("unresolved_location"):
        base.update(
            {
                "needs_user_action": True,
                "next_best_question": "Mình chưa xác định được địa điểm này, bạn có thể nói rõ quận/thành phố không?",
            }
        )
        return base

    if parse_result.get("ambiguous_location") and not has_non_location_filter:
        base.update(
            {
                "needs_user_action": True,
                "needs_confirmation": True,
                "confirmation_type": "explicit",
                "next_best_question": parse_result.get("ambiguous_location_question")
                or "Bạn muốn tìm gần địa điểm nào hoặc ở thành phố nào?",
            }
        )
        base["quick_replies"] = _location_quick_replies(parse_result.get("location_candidates") or [])
        return base

    if (location_status == "ambiguous" or 0.60 <= confidence < 0.75) and not has_non_location_filter:
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

    if not has_usable_filters:
        base.update(
            {
                "needs_user_action": True,
                "next_best_question": _no_signal_question(parse_result),
            }
        )
        base["quick_replies"] = _popular_location_replies() if not parse_result.get("explicit_anywhere") else _quick_replies_for_missing(slots)
        return base

    has_budget = bool(slots.get("budget") or slots.get("budget_max") or slots.get("budget_min"))
    has_guest_count = bool(slots.get("guest_count"))
    has_location = location_mode in {"area", "near_anchor", "near_user", "city_center", "anywhere"} or bool(canonical_area)
    full = bool(has_budget and has_guest_count)
    base["recommendation_level"] = "full" if full else "partial"
    base["can_show_recommendations"] = True
    base["needs_user_action"] = False
    if not has_location and has_non_location_filter:
        base["missing_slots"] = ["location"]

    if location_status == "ok" and canonical_area and 0.75 <= confidence < 0.90:
        base["confirmation_type"] = "implicit"
        base["assumptions"].append(
            {
                "slot": "area",
                "value": canonical_area,
                "confidence": confidence,
                "reason": "fuzzy_location_implicit_match",
            }
        )

    base["next_best_question"] = (
        parse_result.get("ambiguous_location_question")
        if parse_result.get("ambiguous_location")
        else _next_best_question(slots, has_location=has_location)
    )
    base["quick_replies"] = _quick_replies_for_missing(slots, has_location=has_location)
    return base


def _next_best_question(slots: dict[str, Any], *, has_location: bool = False) -> str | None:
    if not has_location and has_non_location_filters(slots):
        return LOCATION_REFINEMENT_QUESTION
    has_known_non_location_filter = any(
        slots.get(key)
        for key in (
            "preferred_type",
            "accommodation_type",
            "accommodation_types",
            "required_amenities",
            "priorities",
            "special_requirements",
        )
    )
    if not has_location and has_known_non_location_filter and not slots.get("guest_count"):
        return "Bạn đi mấy người hoặc ngân sách khoảng bao nhiêu để mình lọc kỹ hơn không?"
    if not has_location and has_known_non_location_filter and not (slots.get("budget") or slots.get("budget_max")):
        return "Ngân sách khoảng bao nhiêu để mình lọc sát hơn không?"
    if not has_location and not slots.get("guest_count"):
        return "Bạn muốn ở khu vực nào hoặc đi mấy người để mình lọc kỹ hơn không?"
    if not has_location and not (slots.get("budget") or slots.get("budget_max")):
        return "Bạn muốn ở khu vực nào hoặc khoảng ngân sách bao nhiêu để mình lọc kỹ hơn không?"
    if not (slots.get("budget") or slots.get("budget_max") or slots.get("budget_min")):
        return "Nếu muốn lọc sát hơn, bạn cho mình biết thêm khoảng ngân sách/đêm nhé."
    if not slots.get("guest_count"):
        return "Bạn đi mấy người để mình lọc phòng phù hợp hơn nhé?"
    if not slots.get("required_amenities") and not slots.get("priorities"):
        return "Bạn có ưu tiên nào như wifi, gần trung tâm hoặc yên tĩnh không?"
    return None


def _quick_replies_for_missing(slots: dict[str, Any], *, has_location: bool = False) -> list[dict]:
    replies: list[dict] = []
    if not has_location:
        replies.extend(_popular_location_replies())
    if not (slots.get("budget") or slots.get("budget_max") or slots.get("budget_min")):
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


def _has_usable_slot(slots: dict[str, Any]) -> bool:
    return any(
        bool(slots.get(key))
        for key in (
            "area",
            "budget",
            "budget_min",
            "budget_max",
            "guest_count",
            "preferred_type",
            "accommodation_type",
            "accommodation_types",
            "required_amenities",
            "priorities",
            "special_requirements",
            "room_count",
            "rating",
        )
    )


def _has_non_location_filter(parse_result: dict, slots: dict[str, Any]) -> bool:
    filters = (parse_result.get("filter_tree") or {}).get("filters") or []
    if any(node.get("key") != "location" for node in filters if isinstance(node, dict)):
        return True
    return has_non_location_filters(slots)


def has_non_location_filters(slots: dict[str, Any] | None) -> bool:
    slots = slots or {}
    return any(bool(slots.get(key)) for key in NON_LOCATION_FILTER_KEYS)


def _no_signal_question(parse_result: dict) -> str:
    if parse_result.get("explicit_anywhere"):
        return "Được, vậy bạn cho mình thêm ngân sách, số người hoặc tiện nghi mong muốn nhé?"
    return "Bạn muốn tìm loại chỗ ở nào hoặc khu vực nào rõ hơn không?"


def _location_quick_replies(candidates: list[dict]) -> list[dict]:
    replies = []
    for candidate in candidates[:5]:
        name = candidate.get("canonical_area") or candidate.get("name")
        if name:
            replies.append({"label": name, "payload": candidate.get("payload") or {"area": name}})
    return replies


def _popular_location_replies() -> list[dict]:
    return [
        {"label": "TP HCM", "payload": {"area": "TP HCM"}},
        {"label": "Hà Nội", "payload": {"area": "Hà Nội"}},
        {"label": "Đà Lạt", "payload": {"area": "Đà Lạt"}},
    ]
