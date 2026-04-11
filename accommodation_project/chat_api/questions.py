from __future__ import annotations

from .schema import CORE_SLOTS, SLOTS


def build_suggested_questions(
    missing_slots: list[str],
    locale: str,
    should_ask_optional: bool,
    slots: dict | None = None,
) -> list[str]:
    slots = slots or {}

    for k in CORE_SLOTS:
        if k in missing_slots:
            spec = SLOTS[k]
            if locale == "en":
                return [spec.question_en or "Could you provide more details?"]
            return [spec.question_vi or "Bạn bổ sung giúp mình thông tin còn thiếu nhé."]

    if should_ask_optional:
        if not slots.get("preferred_type"):
            if locale == "en":
                return ["Do you prefer hotel, homestay, hostel, or apartment?"]
            return ["Bạn thích khách sạn, homestay, hostel hay căn hộ?"]

        if not slots.get("required_amenities"):
            if locale == "en":
                return ["Any must-have amenities like wifi, parking, pool, AC, or kitchen?"]
            return ["Bạn có tiện nghi bắt buộc nào không như wifi, đỗ xe, hồ bơi, điều hòa hay bếp?"]

        if locale == "en":
            return ["Any extra preferences like quiet place, near center, or privacy?"]
        return ["Bạn có ưu tiên thêm như yên tĩnh, gần trung tâm hoặc riêng tư không?"]

    return []