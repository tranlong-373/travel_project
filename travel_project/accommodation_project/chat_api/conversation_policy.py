from __future__ import annotations

import re
from typing import Any

from .normalizers import normalize_key

CONVERSATION_CONFIRM_KEYS = [
    "confirm_table",
    "confirmation_heading",
    "confirmation_prompt",
    "confirmation_options",
]

ACCOMMODATION_HINTS = {
    "khach san",
    "cho o",
    "phong",
    "homestay",
    "hostel",
    "resort",
    "can ho",
    "nha nghi",
    "tim",
    "goi y",
    "de xuat",
    "dat",
    "o dau",
    "khu vuc",
    "quan",
    "district",
    "budget",
    "ngan sach",
    "gia",
    "nguoi",
    "ngay",
    "dem",
    "wifi",
    "ho boi",
}

GREETING_PATTERNS = [
    r"\b(?:chao|hello|hi|hey|xin chao|alo)\b",
]
THANKS_PATTERNS = [
    r"\b(?:cam on|thanks|thank you|thank|ok cam on|okay cam on)\b",
]
GOODBYE_PATTERNS = [
    r"\b(?:tam biet|bye|goodbye|hen gap lai)\b",
]
HELP_PATTERNS = [
    r"\b(?:ban lam duoc gi|co the giup gi|huong dan|giup minh|help)\b",
]
OFF_TOPIC_PATTERNS = [
    r"\b(?:thoi tiet|tin tuc|bai hat|mon an|code giup|lap trinh)\b",
]


def decorate_conversation_response(
    text: str,
    result: dict[str, Any],
    *,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intent = detect_conversation_intent(text)
    if intent is None:
        return result

    decorated = dict(result)
    message = build_conversation_message(intent, locale=locale, context_slots=context_slots)
    decorated["conversation_intent"] = intent
    decorated["bot_message"] = message
    decorated["follow_up_question"] = message
    decorated["suggested_questions"] = [message]
    decorated["ready_for_recommendation"] = False
    decorated["should_ask_optional"] = False
    decorated["awaiting_confirmation"] = False
    decorated["confirmation_required"] = False
    for key in CONVERSATION_CONFIRM_KEYS:
        decorated.pop(key, None)
    return decorated


def detect_conversation_intent(text: str) -> str | None:
    norm = normalize_key(text)
    if not norm:
        return None
    if _looks_like_accommodation_request(norm):
        return None
    if _matches_any(norm, GREETING_PATTERNS):
        return "greeting"
    if _matches_any(norm, THANKS_PATTERNS):
        return "thanks"
    if _matches_any(norm, GOODBYE_PATTERNS):
        return "goodbye"
    if _matches_any(norm, HELP_PATTERNS):
        return "help"
    if _matches_any(norm, OFF_TOPIC_PATTERNS):
        return "off_topic"
    return None


def build_conversation_message(
    intent: str,
    *,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
) -> str:
    has_context = _has_context_slots(context_slots)
    if locale == "en":
        return _english_message(intent, has_context=has_context)
    return _vietnamese_message(intent, has_context=has_context)


def _vietnamese_message(intent: str, *, has_context: bool) -> str:
    if intent == "greeting":
        if has_context:
            return "Chào bạn, mình đây. Mình vẫn giữ thông tin trước đó; bạn muốn đổi khu vực, ngân sách hay thêm tiện nghi nào?"
        return "Chào bạn, mình đây. Bạn muốn tìm chỗ ở khu vực nào?"
    if intent == "thanks":
        return "Không có gì, mình sẵn sàng hỗ trợ. Bạn muốn bổ sung yêu cầu nào cho chỗ ở không?"
    if intent == "goodbye":
        return "Hẹn gặp lại bạn. Khi cần tìm chỗ ở, cứ nhắn mình nhé."
    if intent == "help":
        return "Mình có thể giúp bạn chọn chỗ ở theo khu vực, ngân sách, số người, số ngày, loại chỗ ở và tiện nghi. Bạn muốn ở khu vực nào?"
    return "Mình chủ yếu hỗ trợ chọn chỗ ở du lịch. Bạn muốn tìm ở khu vực nào?"


def _english_message(intent: str, *, has_context: bool) -> str:
    if intent == "greeting":
        if has_context:
            return "Hi, I am here. I still have your previous details; would you like to change the area, budget, or amenities?"
        return "Hi, I am here. Which area would you like to stay in?"
    if intent == "thanks":
        return "You are welcome. Would you like to add any accommodation preferences?"
    if intent == "goodbye":
        return "See you later. Message me anytime you want help finding a place to stay."
    if intent == "help":
        return "I can help choose stays by area, budget, guests, trip length, type, and amenities. Which area do you prefer?"
    return "I mainly help with travel accommodation choices. Which area would you like to stay in?"


def _looks_like_accommodation_request(norm: str) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", norm) for hint in ACCOMMODATION_HINTS)


def _matches_any(norm: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, norm) for pattern in patterns)


def _has_context_slots(context_slots: dict[str, Any] | None) -> bool:
    if not isinstance(context_slots, dict):
        return False
    for value in context_slots.values():
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, tuple, set, dict)) and value:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
    return False
