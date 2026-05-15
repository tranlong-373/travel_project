from __future__ import annotations

import json
import os
from typing import Any


SYSTEM_INSTRUCTION = """
Bạn là correction layer cho hệ thống tìm chỗ ở. Rule/fuzzy parser đã chạy trước bạn.
Nhiệm vụ duy nhất: sửa nhẹ câu lỗi và trích xuất JSON hợp lệ khi rule chưa chắc.
Không tư vấn dài dòng, không giải thích, không dùng markdown, không bịa slot.
Nếu không chắc giá trị nào thì để null hoặc list rỗng.
Nếu câu không liên quan tìm khách sạn, homestay hoặc chỗ ở, trả intent="off_topic".
""".strip()


SCHEMA_INSTRUCTION = """
Output JSON thuần theo schema:
{
  "corrected_text": string,
  "intent": "recommend_accommodation"|"clarify_slot"|"change_slot"|"off_topic"|"unknown",
  "slots": {
    "area": string|null,
    "budget_min": integer|null,
    "budget_max": integer|null,
    "guest_count": integer|null,
    "preferred_type": "hotel"|"homestay"|"hostel"|"apartment"|"resort"|"villa"|null,
    "required_amenities": string[],
    "priorities": string[],
    "special_requirements": string[]
  },
  "slot_confidence": {
    "area": number,
    "budget": number,
    "guest_count": number
  },
  "assumptions": string[],
  "needs_confirmation": boolean,
  "recommendation_level": "none"|"partial"|"full",
  "missing_slots": string[],
  "follow_up_question": string|null,
  "ready_for_recommendation": boolean
}

Normalization:
- "tầm", "khoảng", "budget", "ngân sách", "dưới", "đổ lại", "không quá" là ngân sách.
- "700k" = 700000, "1 triệu"/"1tr"/"1m" = 1000000, "1tr2" = 1200000.
- "từ 500 đến 900k" -> budget_min=500000, budget_max=900000.
- "gần trung tâm", "thuận tiện" -> priorities near_center/convenient.
- "yên tĩnh" -> quiet, "view đẹp" -> nice_view, "gần biển" -> near_beach.
- "sạch sẽ" -> clean, "giá rẻ" -> cheap, "đánh giá cao" -> high_rating.
- "đi công tác", "làm việc", "bàn làm việc", "wifi mạnh" -> special_requirements work_friendly.
- "gia đình" -> family_friendly; nếu có số người thì dùng số đó.
- "couple", "cặp đôi", "người yêu" -> guest_count=2 và special_requirements couple_friendly.
- "1 mình", "solo", "đi công tác 1 người" -> guest_count=1.
- Amenities chuẩn: wifi, pool, parking, air_conditioner, breakfast, balcony, bathtub, kitchen, washing_machine.
- missing_slots chỉ dùng các key core: area, budget, guest_count.
- Nếu user nói chưa biết ở đâu, area=null và hỏi khu vực muốn đi.
- Nếu có area nhưng thiếu budget/guest_count, recommendation_level="partial".
- Không tự bịa địa điểm ngoài supported_locations nếu danh sách được truyền vào.
- Nếu địa điểm không nằm trong supported_locations hoặc không chắc, area=null.
- Trả JSON hợp lệ, không kèm văn bản ngoài JSON.
""".strip()


FEW_SHOT_EXAMPLES = [
    (
        "mình muốn tìm homestay ở Đà Lạt tầm 700k cho 2 người",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": "đà lạt",
                "budget_min": None,
                "budget_max": 700000,
                "guest_count": 2,
                "preferred_type": "homestay",
                "required_amenities": [],
                "priorities": [],
                "special_requirements": [],
            },
            "missing_slots": [],
            "follow_up_question": None,
            "ready_for_recommendation": True,
        },
    ),
    (
        "có chỗ nào gần trung tâm, yên tĩnh, có wifi mạnh để làm việc không",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": None,
                "budget_min": None,
                "budget_max": None,
                "guest_count": None,
                "preferred_type": None,
                "required_amenities": ["wifi"],
                "priorities": ["near_center", "quiet"],
                "special_requirements": ["work_friendly"],
            },
            "missing_slots": ["area", "budget", "guest_count"],
            "follow_up_question": "Bạn muốn ở khu vực nào, ngân sách khoảng bao nhiêu và đi mấy người?",
            "ready_for_recommendation": False,
        },
    ),
    (
        "gia đình 4 người cần khách sạn ở Vũng Tàu cuối tuần này",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": "vũng tàu",
                "budget_min": None,
                "budget_max": None,
                "guest_count": 4,
                "preferred_type": "hotel",
                "required_amenities": [],
                "priorities": [],
                "special_requirements": ["family_friendly"],
            },
            "missing_slots": ["budget"],
            "follow_up_question": "Ngân sách tối đa của bạn khoảng bao nhiêu VND/đêm?",
            "ready_for_recommendation": False,
        },
    ),
    (
        "tầm 1 triệu đổ lại, ưu tiên sạch sẽ, có hồ bơi",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": None,
                "budget_min": None,
                "budget_max": 1000000,
                "guest_count": None,
                "preferred_type": None,
                "required_amenities": ["pool"],
                "priorities": ["clean"],
                "special_requirements": [],
            },
            "missing_slots": ["area", "guest_count"],
            "follow_up_question": "Bạn muốn ở khu vực nào và đi mấy người?",
            "ready_for_recommendation": False,
        },
    ),
    (
        "cho mình chỗ ở hợp couple, view đẹp, gần biển",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": None,
                "budget_min": None,
                "budget_max": None,
                "guest_count": 2,
                "preferred_type": None,
                "required_amenities": [],
                "priorities": ["nice_view", "near_beach"],
                "special_requirements": ["couple_friendly"],
            },
            "missing_slots": ["area", "budget"],
            "follow_up_question": "Bạn muốn ở khu vực nào và ngân sách tối đa khoảng bao nhiêu VND/đêm?",
            "ready_for_recommendation": False,
        },
    ),
    (
        "đi công tác 1 người, cần nơi yên tĩnh, có bàn làm việc",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": None,
                "budget_min": None,
                "budget_max": None,
                "guest_count": 1,
                "preferred_type": None,
                "required_amenities": ["wifi"],
                "priorities": ["quiet"],
                "special_requirements": ["work_friendly"],
            },
            "missing_slots": ["area", "budget"],
            "follow_up_question": "Bạn muốn ở khu vực nào và ngân sách tối đa khoảng bao nhiêu VND/đêm?",
            "ready_for_recommendation": False,
        },
    ),
    (
        "mình chưa biết ở đâu, bạn gợi ý giúp nơi phù hợp ngân sách 800k",
        {
            "intent": "recommend_accommodation",
            "slots": {
                "area": None,
                "budget_min": None,
                "budget_max": 800000,
                "guest_count": None,
                "preferred_type": None,
                "required_amenities": [],
                "priorities": [],
                "special_requirements": [],
            },
            "missing_slots": ["area", "guest_count"],
            "follow_up_question": "Bạn đi mấy người và muốn ở khu vực nào?",
            "ready_for_recommendation": False,
        },
    ),
]


def _example_limit() -> int:
    try:
        value = int(os.getenv("CHAT_API_PROMPT_EXAMPLE_COUNT", "5"))
    except (TypeError, ValueError):
        return 5
    return max(0, min(value, len(FEW_SHOT_EXAMPLES)))


def build_messages(text: str, *, locale: str = "vi", context_slots: dict[str, Any] | None = None) -> list[dict[str, str]]:
    examples_to_use = FEW_SHOT_EXAMPLES[:_example_limit()]
    examples = "\n".join(
        "Input: "
        + input_text
        + "\nOutput: "
        + json.dumps(output, ensure_ascii=False)
        for input_text, output in examples_to_use
    )
    context = json.dumps(context_slots or {}, ensure_ascii=False)
    try:
        from ..location_gazetteer import load_supported_locations

        supported_locations = [item["canonical_name"] for item in load_supported_locations()]
    except Exception:
        supported_locations = []
    supported_location_text = json.dumps(supported_locations[:120], ensure_ascii=False)
    user_prompt = f"""
{SCHEMA_INSTRUCTION}

Few-shot examples:
{examples}

Locale: {locale}
Previous context_slots: {context}
Supported locations: {supported_location_text}
User input: {text}

Chỉ trả JSON hợp lệ, không markdown, không giải thích.
""".strip()

    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user_prompt},
    ]


def build_plain_prompt(text: str, *, locale: str = "vi", context_slots: dict[str, Any] | None = None) -> str:
    messages = build_messages(text, locale=locale, context_slots=context_slots)
    return "\n\n".join(f"{message['role'].upper()}:\n{message['content']}" for message in messages)
