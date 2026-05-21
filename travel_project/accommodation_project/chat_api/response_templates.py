from __future__ import annotations

from typing import Any

from .suggestion_service import display_amenity_label


def build_partial_message(slots, assumptions=None, next_best_question=None) -> str:
    area = _area(slots)
    if area:
        intro = f"Được nhé, mình sẽ gợi ý trước một vài chỗ ở phù hợp tại {area}."
    else:
        filter_phrase = _filter_phrase(slots)
        intro = (
            f"Được nhé, mình đã hiểu bạn muốn tìm {filter_phrase}. "
            "Mình sẽ gợi ý trước vài lựa chọn phù hợp."
        )
    if assumptions:
        intro = f"Mình đoán bạn muốn tìm ở {area or 'khu vực này'}. Mình gợi ý trước vài lựa chọn phù hợp nhé."
    if not area:
        return f"{intro} Nếu muốn lọc sát hơn, bạn cho mình thêm khu vực hoặc địa danh gần đó nhé."
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
    return "Mình chuyên tìm khách sạn, homestay và chỗ ở thôi nha. Bạn muốn tìm chỗ ở ở đâu, mình gợi ý liền."


def build_unknown_message() -> str:
    return "Mình chưa hiểu rõ lắm. Bạn thử nhắn kiểu: \"Khách sạn ở Quận 1 cho 2 người khoảng 800k/đêm\" nhé, mình sẽ tìm ngay."


def build_help_message() -> str:
    return "Mình có thể gợi ý khách sạn, homestay hoặc chỗ ở theo khu vực, ngân sách, số người và tiện ích bạn muốn."


def build_multiple_choice_message(candidates) -> str:
    names = _candidate_names(candidates)
    if names and _looks_like_area_candidates(candidates):
        return f"Mình thấy vài khu vực khác nhau: {names}. Bạn muốn chọn khu vực nào?"
    if names:
        return f"Mình thấy vài địa điểm khác nhau: {names}. Bạn chọn đúng địa chỉ giúp mình nhé?"
    return "Mình thấy có nhiều địa điểm gần đúng. Bạn chọn một địa điểm giúp mình nhé?"


def build_conflict_message(location_info) -> str:
    candidates = location_info.get("location_candidates") if isinstance(location_info, dict) else []
    names = _candidate_names(candidates)
    if names:
        return f"Mình thấy các địa điểm chưa cùng khu vực ({names}). Bạn xác nhận lại khu vực muốn tìm giúp mình nhé?"
    return "Mình thấy khu vực trong câu hơi mâu thuẫn. Bạn xác nhận lại nơi muốn tìm giúp mình nhé?"


def build_greeting_message() -> str:
    return "Chào bạn! Bạn muốn tìm chỗ ở ở đâu, mình gợi ý ngay nhé."


def build_thanks_message() -> str:
    return "Vui lòng giúp được bạn! Lần sau cần tìm chỗ ở cứ nhắn mình nha."


def build_goodbye_message() -> str:
    return "Bái bai bạn, chúc bạn có chuyến đi vui! Lần sau cần gợi ý chỗ ở cứ nhắn mình nha."


def build_unsupported_message() -> str:
    return "Khu vực này mình chưa có dữ liệu đầy đủ. Bạn thử nhắn khu vực khác gần đó xem sao nha."


def build_unresolved_location_message() -> str:
    return "Bạn muốn tìm ở khu vực nào? Nhắn tên quận hoặc thành phố là mình tìm ngay nhé."


def build_unresolved_place_message() -> str:
    return "Mình chưa tìm được địa danh này. Bạn thêm tên quận hoặc thành phố vào giúp mình nhé, ví dụ: 'gần Vincom Quận 1' hay 'gần chợ Bến Thành Quận 1'."


# ── Input-type-aware messages ─────────────────────────────────────────────────

def build_hotel_name_message(hotel_name: str | None, area: str | None = None) -> str:
    """Message khi bot nhận ra user đang tìm theo tên khách sạn cụ thể."""
    name_part = f'"{hotel_name}"' if hotel_name else "tên này"
    area_part = f" tại {area}" if area else ""
    return (
        f"Mình tìm thấy chỗ ở khớp với {name_part}{area_part}. "
        "Mình cũng gợi ý thêm các chỗ ở tên tương tự bạn có thể tham khảo."
    )


def build_address_search_message(address_phrase: str | None = None) -> str:
    """Message khi bot nhận ra user nhập địa chỉ cụ thể."""
    addr_part = f'"{address_phrase}"' if address_phrase else "địa chỉ bạn nhập"
    return (
        f"Mình đã xác định {addr_part}. "
        "Đây là các chỗ ở gần khu vực đó, được sắp xếp theo khoảng cách."
    )


def build_landmark_search_message(landmark_name: str | None, resolved: bool = True) -> str:
    """Message khi bot nhận ra user tìm gần một địa danh cụ thể."""
    place_part = f"gần {landmark_name}" if landmark_name else "khu vực bạn chọn"
    if not resolved:
        return (
            f"Mình chưa tìm được tọa độ của {landmark_name or 'địa danh này'}. "
            "Bạn thêm tên quận hoặc thành phố vào giúp mình nhé, ví dụ: "
            f'"{landmark_name or "địa danh"} Quận 1".'
        )
    return f"Để mình tìm các chỗ ở {place_part} cho bạn nhé."


def build_unresolved_place_with_filters_message(slots: dict[str, Any], place_name: str | None) -> str:
    return (
        f"Mình đã hiểu các tiêu chí như {_filter_phrase(slots)}. "
        f"Riêng địa danh {place_name or 'này'} mình chưa xác định chắc, "
        "bạn có thể nhập thêm quận/thành phố hoặc chọn một gợi ý gần đúng không?"
    )


def _area(slots: dict[str, Any]) -> str:
    return slots.get("area") or slots.get("canonical_area") or ""


def _looks_like_area_candidates(candidates) -> bool:
    values = [candidate for candidate in candidates or [] if isinstance(candidate, dict)]
    if not values:
        return False
    return all(candidate.get("source") == "area" or candidate.get("area_id") for candidate in values)


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
        name = candidate.get("canonical_area") or candidate.get("name") if isinstance(candidate, dict) else None
        if name and name not in names:
            names.append(name)
    return ", ".join(names[:4])


def _filter_phrase(slots: dict[str, Any]) -> str:
    parts: list[str] = []
    types = slots.get("accommodation_types") or []
    if isinstance(types, str):
        types = [types]
    if not types and (slots.get("preferred_type") or slots.get("accommodation_type")):
        types = [slots.get("preferred_type") or slots.get("accommodation_type")]
    if types:
        parts.append("loại " + ", ".join(str(item) for item in types))
    amenities = slots.get("required_amenities") or slots.get("amenities") or []
    if amenities:
        parts.append("tiện nghi " + ", ".join(display_amenity_label(item) for item in amenities))
    if slots.get("budget") or slots.get("budget_max") or slots.get("budget_min"):
        parts.append("ngân sách")
    if slots.get("guest_count"):
        parts.append(f"{slots['guest_count']} khách")
    if slots.get("room_count"):
        parts.append(f"{slots['room_count']} phòng")
    if slots.get("priorities"):
        parts.append("ưu tiên " + ", ".join(str(item) for item in slots["priorities"]))
    if slots.get("special_requirements"):
        parts.append("yêu cầu " + ", ".join(str(item) for item in slots["special_requirements"]))
    return "; ".join(parts) if parts else "các tiêu chí này"
