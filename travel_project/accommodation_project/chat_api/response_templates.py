from __future__ import annotations

from typing import Any


def build_partial_message(slots, assumptions=None, next_best_question=None) -> str:
    area = _area(slots)
    if area:
        intro = f"Được nhé, mình sẽ gợi ý trước một vài chỗ ở phù hợp tại {area}."
    else:
        intro = "Được nhé, mình sẽ gợi ý trước một vài chỗ ở phù hợp với điều kiện bạn vừa nói."
    if assumptions:
        intro = f"Mình đoán bạn muốn tìm ở {area or 'khu vực này'}. Mình gợi ý trước vài lựa chọn phù hợp nhé."
    missing_hint = _missing_essential_hint(slots)
    if missing_hint:
        return f"{intro} Nếu muốn lọc sát hơn, bạn cho mình biết thêm {missing_hint} nhé."
    return intro


def build_full_message(slots) -> str:
    if slots.get("area") or slots.get("canonical_area"):
        return "Mình đã có đủ thông tin cơ bản rồi. Mình sẽ tìm các chỗ ở phù hợp nhất với khu vực, ngân sách và số người của bạn nhé."
    return "Mình đã có ngân sách và số người rồi. Mình sẽ gợi ý các chỗ ở phù hợp trước, bạn có thể bổ sung khu vực sau nhé."


def build_implicit_confirmation_message(assumption) -> str:
    area = assumption.get("value") if isinstance(assumption, dict) else assumption
    return f"Mình đoán bạn muốn tìm ở {area}. Mình gợi ý trước vài lựa chọn phù hợp nhé. Nếu không đúng, bạn có thể nhắn lại khu vực giúp mình."


def build_explicit_confirmation_message(candidates) -> str:
    if candidates:
        first = candidates[0].get("canonical_area")
        if first:
            return f"Mình chưa chắc khu vực bạn muốn tìm là {first} đúng không?"
    return "Mình chưa chắc khu vực bạn muốn tìm. Bạn xác nhận lại giúp mình nhé?"


def build_off_topic_message() -> str:
    return "Mình hiện hỗ trợ tốt nhất phần tìm khách sạn, homestay và chỗ ở du lịch. Bạn có thể nhắn khu vực muốn đi, mình sẽ gợi ý trước cho bạn nhé."


def build_unknown_message() -> str:
    return "Mình chưa hiểu rõ nhu cầu của bạn lắm. Bạn có thể nhắn theo kiểu: 'Tìm khách sạn ở Quận 5 cho 2 người khoảng 800k/đêm' nhé."


def build_help_message() -> str:
    return "Mình có thể gợi ý khách sạn, homestay hoặc chỗ ở theo khu vực, ngân sách, số người và tiện ích bạn muốn."


def build_multiple_choice_message(candidates) -> str:
    names = _candidate_names(candidates)
    if names:
        return f"Mình thấy vài khu vực khác nhau: {names}. Bạn muốn chọn khu vực nào?"
    return "Mình thấy có nhiều khu vực trong câu. Bạn muốn chọn một khu vực nào?"


def build_conflict_message(location_info) -> str:
    candidates = location_info.get("location_candidates") if isinstance(location_info, dict) else []
    names = _candidate_names(candidates)
    if names:
        return f"Mình thấy các địa điểm chưa cùng khu vực ({names}). Bạn xác nhận lại khu vực muốn tìm giúp mình nhé?"
    return "Mình thấy khu vực trong câu hơi mâu thuẫn. Bạn xác nhận lại nơi muốn tìm giúp mình nhé?"


def build_greeting_message() -> str:
    return "Chào bạn, mình đây. Bạn nhắn khu vực muốn đi, mình sẽ gợi ý chỗ ở trước cho bạn nhé."


def build_thanks_message() -> str:
    return "Không có gì, mình luôn sẵn sàng hỗ trợ bạn tìm chỗ ở phù hợp."


def build_goodbye_message() -> str:
    return "Hẹn gặp lại bạn. Khi cần tìm chỗ ở, cứ nhắn mình nhé."


def build_unsupported_message() -> str:
    return "Khu vực này hiện mình chưa chắc có dữ liệu phù hợp. Bạn nhắn lại khu vực muốn tìm giúp mình nhé."


def build_unresolved_location_message() -> str:
    return "Bạn muốn tìm chỗ ở khu vực nào? Chỉ cần nhắn tên quận hoặc thành phố là được nhé."


def build_unresolved_place_message() -> str:
    return "Mình chưa xác định được địa điểm này, bạn có thể nói rõ quận/thành phố không?"


def _area(slots: dict[str, Any]) -> str:
    return slots.get("area") or slots.get("canonical_area") or ""


def _missing_essential_hint(slots: dict[str, Any]) -> str:
    missing = []
    if not (slots.get("budget") or slots.get("budget_max") or slots.get("budget_min")):
        missing.append("khoảng ngân sách/đêm")
    if not slots.get("guest_count"):
        missing.append("số khách")
    if not slots.get("trip_days"):
        missing.append("số ngày ở")

    if not missing:
        return ""
    if len(missing) == 1:
        return missing[0]
    return ", ".join(missing[:-1]) + " và " + missing[-1]


def _candidate_names(candidates) -> str:
    names = []
    for candidate in candidates or []:
        name = candidate.get("canonical_area") if isinstance(candidate, dict) else None
        if name and name not in names:
            names.append(name)
    return ", ".join(names[:4])
