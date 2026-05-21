from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

SlotLevel = Literal["core", "optional"]


@dataclass(frozen=True)
class SlotSpec:
    key: str
    level: SlotLevel
    value_type: str
    description: str
    allowed: Optional[set[str]] = None
    question_vi: Optional[str] = None
    question_en: Optional[str] = None


SCHEMA_VERSION = "2.0"
INTENT_DEFAULT = "recommend_accommodation"

# Đồng bộ với DB/recommend hiện tại của bạn cậu
ALLOWED_TYPES = {"hotel", "homestay", "hostel", "apartment"}

ALLOWED_AMENITIES = {
    "wifi",
    "pool",
    "parking",
    "air_conditioner",
    "breakfast",
    "balcony",
    "bathtub",
    "kitchen",
    "washing_machine",
}

ALLOWED_PRIORITIES = {
    "near_center",
    "near_beach",
    "cheap",
    "quiet",
    "high_rating",
    "nice_view",
}

ALLOWED_SPECIAL_REQUIREMENTS = {
    "baby_friendly",
    "elderly_friendly",
    "pet_friendly",
    "work_friendly",
    "private",
    "safe_area",
}

SLOTS: dict[str, SlotSpec] = {
    "area": SlotSpec(
        key="area",
        level="core",
        value_type="str",
        description="Khu vực user muốn ở.",
        question_vi="Bạn muốn ở khu vực nào?",
        question_en="Where do you want to stay?",
    ),
    "budget": SlotSpec(
        key="budget",
        level="core",
        value_type="int",
        description="Ngân sách tối đa VND/đêm.",
        question_vi="Ngân sách tối đa của bạn khoảng bao nhiêu VND/đêm?",
        question_en="What is your max budget per night in VND?",
    ),
    "guest_count": SlotSpec(
        key="guest_count",
        level="core",
        value_type="int",
        description="Số khách.",
        question_vi="Bạn đi mấy người?",
        question_en="How many guests?",
    ),
    "preferred_type": SlotSpec(
        key="preferred_type",
        level="optional",
        value_type="str",
        description="Loại chỗ ở.",
        allowed=ALLOWED_TYPES,
        question_vi="Bạn thích khách sạn, homestay, hostel hay căn hộ?",
        question_en="Do you prefer hotel, homestay, hostel, or apartment?",
    ),
    "accommodation_type": SlotSpec(
        key="accommodation_type",
        level="optional",
        value_type="str",
        description="Alias mềm của preferred_type cho parser/LLM JSON.",
        allowed=ALLOWED_TYPES,
    ),
    "accommodation_types": SlotSpec(
        key="accommodation_types",
        level="optional",
        value_type="list[str]",
        description="Danh sách loại chỗ ở user chấp nhận, dùng OR khi có nhiều loại.",
        allowed=ALLOWED_TYPES,
    ),
    "required_amenities": SlotSpec(
        key="required_amenities",
        level="optional",
        value_type="list[str]",
        description="Tiện nghi bắt buộc.",
        allowed=ALLOWED_AMENITIES,
        question_vi="Bạn có tiện nghi bắt buộc nào không, như wifi, hồ bơi, đỗ xe, điều hòa, bếp...?",
        question_en="Any must-have amenities like wifi, pool, parking, AC, kitchen...?",
    ),
    "priorities": SlotSpec(
        key="priorities",
        level="optional",
        value_type="list[str]",
        description="Tiêu chí ưu tiên.",
        allowed=ALLOWED_PRIORITIES,
        question_vi="Bạn ưu tiên gì hơn: gần trung tâm, gần biển, yên tĩnh, rẻ hay view đẹp?",
        question_en="What matters most: near center, near beach, quiet, cheap, or nice view?",
    ),
    "special_requirements": SlotSpec(
        key="special_requirements",
        level="optional",
        value_type="list[str]",
        description="Nhu cầu đặc biệt.",
        allowed=ALLOWED_SPECIAL_REQUIREMENTS,
        question_vi="Bạn có yêu cầu đặc biệt nào không: em bé, người lớn tuổi, thú cưng, làm việc, riêng tư, an toàn?",
        question_en="Any special needs: baby, elderly, pets, work, privacy, safety?",
    ),
    "trip_days": SlotSpec(
        key="trip_days",
        level="core",
        value_type="int",
        description="Số ngày đi.",
        question_vi="Bạn đi mấy ngày?",
        question_en="How many days is your trip?",
    ),
    "room_count": SlotSpec(
        key="room_count",
        level="optional",
        value_type="int",
        description="Số phòng nếu user nói rõ.",
    ),
    "rating": SlotSpec(
        key="rating",
        level="optional",
        value_type="float",
        description="Mức đánh giá tối thiểu nếu user nói rõ.",
    ),
    "check_in": SlotSpec(
        key="check_in",
        level="optional",
        value_type="str",
        description="Ngày nhận phòng nếu user nói rõ.",
    ),
    "check_out": SlotSpec(
        key="check_out",
        level="optional",
        value_type="str",
        description="Ngày trả phòng nếu user nói rõ.",
    ),
    "location_phrase": SlotSpec(
        key="location_phrase",
        level="optional",
        value_type="str",
        description="Cụm địa điểm gốc user nói.",
    ),
    "location_mode": SlotSpec(
        key="location_mode",
        level="optional",
        value_type="str",
        description="anywhere, area, near_anchor, multiple_choice hoặc unknown.",
    ),
}

CORE_SLOTS = [k for (k, s) in SLOTS.items() if s.level == "core"]


def empty_slots() -> dict[str, Any]:
    return {
        "area": None,
        "budget": None,
        "guest_count": None,
        "preferred_type": None,
        "accommodation_type": None,
        "accommodation_types": [],
        "required_amenities": [],
        "priorities": [],
        "special_requirements": [],
        "trip_days": None,
        "room_count": None,
        "rating": None,
        "check_in": None,
        "check_out": None,
        "location_phrase": None,
        "location_mode": "unknown",
    }
