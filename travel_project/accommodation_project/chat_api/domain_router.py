from __future__ import annotations

import re
from typing import Any

from .text_normalizer import normalize_user_text


TERMINAL_INTENTS = {"greeting", "thanks", "goodbye", "help", "off_topic", "unknown"}

_GREETING_PATTERNS = [
    r"\b(?:xin chao|chao|hello|hi|alo|e ban)\b",
]
_THANKS_PATTERNS = [
    r"\b(?:cam on|thanks|thank you|ok cam on|okay cam on)\b",
]
_GOODBYE_PATTERNS = [
    r"\b(?:tam biet|bye|goodbye|hen gap lai)\b",
]
_HELP_PATTERNS = [
    r"\b(?:bot lam duoc gi|giup toi|giup minh|huong dan|help)\b",
]
_OFF_TOPIC_PATTERNS = [
    r"\b(?:thoi tiet|troi mua|troi nang|tin tuc|bai hat|game|viet code|code giup|lap trinh|bai tap|hoc tap)\b",
]
_CONFIRM_YES_PATTERNS = [
    r"^(?:dung|dung roi|ok|oke|uh|u|co|yes|chinh xac|duoc)$",
]
_CONFIRM_NO_PATTERNS = [
    r"^(?:khong|ko|hong|sai|khong phai|no|doi lai)$",
]
_CHANGE_SLOT_PATTERNS = [
    r"\b(?:doi|chuyen|thoi lay|lay|sua|cap nhat)\b",
    r"\bngan sach\s+(?:doi|chuyen|sua)\b",
]
_ACCOMMODATION_HINTS = [
    "khach san",
    "ks",
    "ksan",
    "hotel",
    "homestay",
    "homstay",
    "hostel",
    "phong",
    "cho o",
    "can ho",
    "apartment",
    "villa",
    "resort",
    "du lich",
    "di quan",
    "di da lat",
    "di ha noi",
    "di tp hcm",
    "di dau cung duoc",
    "ngan sach",
    "budget",
    "nguoi",
    "wifi",
    "wf",
    "may lanh",
    "dieu hoa",
    "gan trung tam",
    "yen tinh",
    "view dep",
    "landmark",
]
_SHORT_SLOT_PATTERNS = [
    r"^\d+\s*(?:nguoi|ng|khach)$",
    r"^(?:mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+nguoi$",
    r"^\d+(?:[.,]\d+)?\s*(?:k|tr|trieu|m|million)$",
    r"^\d+\s*(?:ngay|dem)$",
    r"^(?:co\s+)?(?:wifi|wf|may lanh|dieu hoa|gan trung tam|yen tinh|view dep)$",
]


def classify_message(text: str, context_slots: dict | None = None, locale: str = "vi") -> dict:
    normalized = normalize_user_text(text)
    norm = normalized["no_accent_text"]
    compact = normalized["compact_text"]
    has_context = _has_context_slots(context_slots)

    if not norm:
        return {"intent": "unknown", "confidence": 0.95, "reason": "empty_input"}

    if has_context and (compact.isdigit() or norm in {"mot", "hai", "ba", "bon", "tu", "nam", "sau", "bay", "tam", "chin", "muoi"}):
        return {"intent": "clarify_slot", "confidence": 0.86, "reason": "bare_number_context_follow_up"}

    if _is_noise(norm, compact):
        return {"intent": "unknown", "confidence": 0.9, "reason": "low_information_noise"}

    if _matches_any(norm, _CONFIRM_YES_PATTERNS) and has_context:
        return {"intent": "confirm_yes", "confidence": 0.9, "reason": "short_confirmation_yes"}
    if _matches_any(norm, _CONFIRM_NO_PATTERNS) and has_context:
        return {"intent": "confirm_no", "confidence": 0.9, "reason": "short_confirmation_no"}

    if _matches_any(norm, _OFF_TOPIC_PATTERNS):
        return {"intent": "off_topic", "confidence": 0.92, "reason": "off_topic_keyword"}

    if _matches_any(norm, _GREETING_PATTERNS):
        return {"intent": "greeting", "confidence": 0.9, "reason": "greeting_keyword"}
    if _matches_any(norm, _THANKS_PATTERNS):
        return {"intent": "thanks", "confidence": 0.9, "reason": "thanks_keyword"}
    if _matches_any(norm, _GOODBYE_PATTERNS):
        return {"intent": "goodbye", "confidence": 0.9, "reason": "goodbye_keyword"}
    if _matches_any(norm, _HELP_PATTERNS):
        return {"intent": "help", "confidence": 0.9, "reason": "help_keyword"}

    if has_context and _matches_any(norm, _CHANGE_SLOT_PATTERNS):
        return {"intent": "change_slot", "confidence": 0.86, "reason": "change_slot_keyword"}

    if has_context and _matches_any(norm, _SHORT_SLOT_PATTERNS):
        return {"intent": "clarify_slot", "confidence": 0.84, "reason": "short_slot_follow_up"}

    if _has_accommodation_signal(norm, compact):
        return {"intent": "recommend_accommodation", "confidence": 0.84, "reason": "accommodation_signal"}

    if has_context and len(norm.split()) <= 4:
        return {"intent": "clarify_slot", "confidence": 0.62, "reason": "short_context_follow_up"}

    return {"intent": "unknown", "confidence": 0.55, "reason": "no_clear_domain_signal"}


def _matches_any(norm: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, norm) for pattern in patterns)


def _has_accommodation_signal(norm: str, compact: str) -> bool:
    if any(re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", norm) for hint in _ACCOMMODATION_HINTS):
        return True
    if re.search(r"\b(?:q|quan|district)\s*\d{1,2}\b", norm):
        return True
    if re.search(r"(?:q|quan)[a-z]*\d{1,3}", compact):
        return True
    if re.search(r"\b\d+\s*(?:nguoi|ng|khach)\b", norm):
        return True
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:k|tr|trieu|m|million)\b", norm):
        return True
    return _has_location_alias_signal(compact)


def _is_noise(norm: str, compact: str) -> bool:
    if norm in {"?", "??", "???", ".", "..", "..."}:
        return True
    if compact in {"abcxyz", "asdf", "qwerty"}:
        return True
    if len(compact) <= 1:
        return True
    return False


def _has_location_alias_signal(compact: str) -> bool:
    if not compact:
        return False
    try:
        from .location_gazetteer import load_supported_locations

        for location in load_supported_locations():
            for alias in location.get("aliases") or []:
                alias_compact = normalize_user_text(alias)["compact_text"]
                if len(alias_compact) >= 5 and alias_compact in compact:
                    return True
    except Exception:
        return False
    return False


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
