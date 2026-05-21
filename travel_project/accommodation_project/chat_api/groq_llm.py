"""
Groq API integration — free-tier LLM backend cho chat_api.

Chỉ kích hoạt khi GROQ_API_KEY được set trong .env.
Dùng để cải thiện intent extraction cho những câu phức tạp
mà rule-based parser không xử lý được tốt.

Free tier (2025): 14,400 req/day với llama-3.3-70b-versatile.
Fallback về rule-based parser nếu Groq unavailable.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT_SECONDS", "8"))
_GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "256"))

# Rate-limit guard: Groq free tier ~30 req/min
_rate_lock = threading.Lock()
_last_call_at: float = 0.0
_MIN_INTERVAL = 0.3  # seconds between calls

_SYSTEM_PROMPT = """Bạn là Travel Accommodation NLU Engine cho chatbot gợi ý nơi ở tại Việt Nam.
Nhiệm vụ: trích xuất thông tin từ câu người dùng và trả về JSON sạch. Chỉ trả JSON, không giải thích.

CÁC TRƯỜNG CẦN TRÍCH XUẤT:
- area: khu vực hành chính (quận/thành phố) — string hoặc null
- nearby_place: địa danh/POI cụ thể cần ở gần — string hoặc null
- budget_max: ngân sách tối đa mỗi đêm — số nguyên VND hoặc null
- guest_count: số người — số nguyên hoặc null
- accommodation_type: hotel | homestay | hostel | apartment | null
- required_amenities: mảng từ [wifi, pool, parking, air_conditioner, kitchen, breakfast]
- input_type: "hotel_name" | "address" | "landmark" | "area_search"

CHUẨN HÓA TÊN KHU VỰC (luôn trả về tên chuẩn):
- "q1", "quan 1", "district 1", "quận 1" → "Quận 1"
- "q3", "quan 3" → "Quận 3"
- "q5", "quan 5" → "Quận 5"
- "q7", "quan 7" → "Quận 7"
- "q10", "quan 10" → "Quận 10"
- "bt", "binh thanh", "bình thạnh" → "Bình Thạnh"
- "binh tan", "bình tân" → "Bình Tân"
- "go vap", "gò vấp" → "Gò Vấp"
- "phu nhuan", "phú nhuận" → "Phú Nhuận"
- "tan binh", "tân bình" → "Tân Bình"
- "tan phu", "tân phú" → "Tân Phú"
- "thu duc", "thủ đức" → "Thủ Đức"
- "hcm", "tphcm", "sài gòn", "saigon", "ho chi minh" → "Hồ Chí Minh"
- "hn", "ha noi", "hà nội", "hanoi" → "Hà Nội"
- "dn", "da nang", "đà nẵng" → "Đà Nẵng"
- "dl", "da lat", "đà lạt" → "Đà Lạt"
- "vt", "vung tau", "vũng tàu" → "Vũng Tàu"
- "hp", "hai phong", "hải phòng" → "Hải Phòng"

PHÂN BIỆT area VÀ nearby_place:
- area: dùng khi là quận, thành phố, khu vực hành chính. Ví dụ: "quận 1", "bình thạnh", "đà lạt"
- nearby_place: dùng khi là địa danh cụ thể, POI, landmark. Ví dụ: "sân bay Tân Sơn Nhất", "chợ Bến Thành", "Nhà thờ Đức Bà", "Landmark 81"
- KHÔNG được: "gần sân bay Tân Sơn Nhất" → area="Tân Sơn Nhất" ✗
- ĐÚNG: "gần sân bay Tân Sơn Nhất" → nearby_place="Sân bay Tân Sơn Nhất", area=null ✓
- Nếu có cả hai: "gần cafe ở quận 3" → area="Quận 3", nearby_place="Quán cafe" ✓

BUDGET PARSING (đổi về số nguyên VND):
- "k" = × 1.000 → "500k" = 500000
- "tr" / "triệu" = × 1.000.000 → "1tr" = 1000000, "1tr5" = 1500000
- "nửa triệu" = 500000
- "800 nghìn" = 800000
- "dưới/tối đa/không quá X" → budget_max = X
- "khoảng/tầm X" → budget_max = X

GUEST COUNT:
- "1 mình", "đi 1 mình", "solo" → 1
- "đi đôi", "2 vợ chồng", "couple" → 2
- "cả nhà 4 người", "nhóm 5 đứa" → đúng số

Ví dụ:
{"area": "Quận 1", "nearby_place": null, "budget_max": 500000, "guest_count": 2, "accommodation_type": "hotel", "required_amenities": ["wifi"], "input_type": "area_search"}
{"area": null, "nearby_place": "Sân bay Tân Sơn Nhất", "budget_max": null, "guest_count": 2, "accommodation_type": null, "required_amenities": [], "input_type": "landmark"}
{"area": "Quận 3", "nearby_place": null, "budget_max": 800000, "guest_count": null, "accommodation_type": "homestay", "required_amenities": ["parking"], "input_type": "area_search"}"""


def is_groq_enabled() -> bool:
    return bool(_GROQ_API_KEY)


def groq_extract_slots(text: str, *, context_slots: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """
    Gọi Groq API để extract slots từ text người dùng.

    Returns:
        dict với các slots đã extract, hoặc None nếu Groq không available / gặp lỗi.
    """
    if not is_groq_enabled():
        return None

    global _last_call_at
    with _rate_lock:
        elapsed = time.monotonic() - _last_call_at
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_call_at = time.monotonic()

    context_hint = ""
    if context_slots:
        filled = {k: v for k, v in context_slots.items() if v is not None and k in
                  ("area", "budget", "guest_count", "accommodation_type")}
        if filled:
            context_hint = f"\nThông tin đã biết từ hội thoại trước: {json.dumps(filled, ensure_ascii=False)}"

    user_message = f"Câu người dùng: {text}{context_hint}"

    try:
        import urllib.request

        payload = json.dumps({
            "model": _GROQ_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": _GROQ_MAX_TOKENS,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {_GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_GROQ_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        content = body["choices"][0]["message"]["content"]
        extracted = json.loads(content)
        if not isinstance(extracted, dict):
            return None
        return _normalize_groq_response(extracted)

    except Exception as exc:
        logger.debug("groq_extract_slots failed: %s", exc)
        return None


def _normalize_groq_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa response từ Groq về format slots chuẩn của chat_api."""
    result: dict[str, Any] = {}

    area = raw.get("area")
    if isinstance(area, str) and area.strip():
        result["area"] = area.strip()

    nearby = raw.get("nearby_place")
    if isinstance(nearby, str) and nearby.strip():
        result["nearby_place"] = nearby.strip()
        result["location_mode"] = "near_anchor"

    budget = raw.get("budget_max")
    if budget is not None:
        try:
            result["budget"] = int(float(str(budget).replace(",", "").replace(".", "")))
        except (ValueError, TypeError):
            pass

    guest_count = raw.get("guest_count")
    if guest_count is not None:
        try:
            result["guest_count"] = int(guest_count)
        except (ValueError, TypeError):
            pass

    acc_type = raw.get("accommodation_type")
    _valid_types = {"hotel", "homestay", "hostel", "apartment"}
    if isinstance(acc_type, str) and acc_type.lower() in _valid_types:
        result["preferred_type"] = acc_type.lower()
        result["accommodation_type"] = acc_type.lower()
        result["accommodation_types"] = [acc_type.lower()]

    amenities = raw.get("required_amenities")
    _valid_amenities = {"wifi", "pool", "parking", "air_conditioner", "kitchen", "breakfast"}
    if isinstance(amenities, list):
        result["required_amenities"] = [a for a in amenities if a in _valid_amenities]

    input_type = raw.get("input_type")
    if input_type in {"hotel_name", "address", "landmark", "area_search"}:
        result["groq_input_type"] = input_type

    return result


def merge_groq_slots(base_slots: dict[str, Any], groq_slots: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge Groq-extracted slots vào base_slots từ rule-based parser.
    Rule-based parser được ưu tiên — Groq chỉ fill những slot còn trống.
    """
    if not groq_slots:
        return base_slots

    merged = dict(base_slots)
    for key, value in groq_slots.items():
        if key == "required_amenities":
            base = merged.get("required_amenities") or []
            merged["required_amenities"] = list(dict.fromkeys(list(base) + list(value or [])))
        elif key not in merged or merged[key] is None:
            merged[key] = value

    return merged
