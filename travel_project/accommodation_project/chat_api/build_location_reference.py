from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

SUPPORTED_AREAS = [
    {
        "id": "tp_hcm",
        "canonical_name": "tp hcm",
        "type": "province_city",
        "parent_id": None,
        "supported": True,
        "aliases": ["tp hcm", "tphcm", "hcm", "hcmc", "ho chi minh", "ho chi minh city", "tp ho chi minh", "thanh pho ho chi minh", "sai gon", "saigon", "sg", "sài gòn", "thành phố hồ chí minh", "tp hồ chí minh", "hồ chí minh"],
    },
    {
        "id": "ha_noi",
        "canonical_name": "hà nội",
        "type": "province_city",
        "parent_id": None,
        "supported": True,
        "aliases": ["ha noi", "hanoi", "hn", "hà nội", "thủ đô", "thu do"],
    },
    {
        "id": "thanh_hoa",
        "canonical_name": "thanh hóa",
        "type": "province",
        "parent_id": None,
        "supported": True,
        "aliases": ["thanh hoa", "thanh hóa", "sam son", "sầm sơn", "tp thanh hoa", "thanh hoa city"],
    },
    {
        "id": "dong_nai",
        "canonical_name": "đồng nai",
        "type": "province",
        "parent_id": None,
        "supported": True,
        "aliases": ["dong nai", "đồng nai", "bien hoa", "biên hòa", "long khanh", "long khánh"],
    },
    {
        "id": "an_giang",
        "canonical_name": "an giang",
        "type": "province",
        "parent_id": None,
        "supported": True,
        "aliases": ["an giang", "long xuyen", "long xuyên", "chau doc", "châu đốc"],
    },
    {
        "id": "binh_dinh",
        "canonical_name": "bình định",
        "type": "province",
        "parent_id": None,
        "supported": True,
        "aliases": ["binh dinh", "bình định", "quy nhon", "quy nhơn"],
    },
]

LANDMARKS = [
    {"name": "Landmark 81", "aliases": ["landmark 81"], "parent_area_id": "tp_hcm", "category": "landmark", "importance": 95},
    {"name": "Bến Thành", "aliases": ["bến thành", "ben thanh", "cho ben thanh", "chợ bến thành"], "parent_area_id": "tp_hcm", "category": "landmark", "importance": 95},
    {"name": "Tân Sơn Nhất", "aliases": ["tân sơn nhất", "tan son nhat", "sân bay tân sơn nhất", "san bay tan son nhat"], "parent_area_id": "tp_hcm", "category": "airport", "importance": 90},
    {"name": "Chợ Rẫy", "aliases": ["chợ rẫy", "cho ray", "bệnh viện chợ rẫy", "benh vien cho ray"], "parent_area_id": "tp_hcm", "category": "landmark", "importance": 85},
    {"name": "Old Quarter", "aliases": ["old quarter", "phố cổ hà nội", "pho co ha noi", "hanoi old quarter"], "parent_area_id": "ha_noi", "category": "landmark", "importance": 95},
    {"name": "Hoàn Kiếm", "aliases": ["hoan kiem", "hoàn kiếm", "hồ hoàn kiếm", "ho hoan kiem"], "parent_area_id": "ha_noi", "category": "landmark", "importance": 90},
    {"name": "Nội Bài", "aliases": ["nội bài", "noi bai", "sân bay nội bài", "san bay noi bai", "noi bai airport"], "parent_area_id": "ha_noi", "category": "airport", "importance": 85},
    {"name": "Biển Sầm Sơn", "aliases": ["biển sầm sơn", "bien sam son", "bãi biển sầm sơn", "sam son beach"], "parent_area_id": "thanh_hoa", "category": "beach", "importance": 80},
    {"name": "Bửu Long", "aliases": ["bửu long", "buu long", "khu du lịch bửu long", "buu long tourist area"], "parent_area_id": "dong_nai", "category": "landmark", "importance": 70},
    {"name": "Núi Cấm", "aliases": ["núi cấm", "nui cam", "cam mountain"], "parent_area_id": "an_giang", "category": "landmark", "importance": 75},
    {"name": "Eo Gió", "aliases": ["eo gió", "eo gio", "ky co", "kỳ co"], "parent_area_id": "binh_dinh", "category": "landmark", "importance": 80},
    {"name": "Đại Nội", "aliases": ["đại nội", "dai noi", "imperial city hue", "hue imperial city"], "parent_area_id": "hue", "category": "unsupported_landmark", "importance": 90},
    {"name": "Phố cổ Hội An", "aliases": ["phố cổ hội an", "pho co hoi an", "hoi an ancient town"], "parent_area_id": "hoi_an", "category": "unsupported_landmark", "importance": 90},
]

LOCATION_RULES = {
    "multiple_choice_phrases": ["hay", "hoac", "hoặc", "or", "either", "deu duoc", "đều được", "cung duoc", "cũng được"],
    "unsupported_areas": [
        {"id": "hue", "canonical_name": "huế", "aliases": ["hue", "huế"]},
        {"id": "da_nang", "canonical_name": "đà nẵng", "aliases": ["da nang", "đà nẵng", "da nang airport", "sân bay đà nẵng", "san bay da nang"]},
        {"id": "da_lat", "canonical_name": "đà lạt", "aliases": ["da lat", "đà lạt"]},
        {"id": "hoi_an", "canonical_name": "hội an", "aliases": ["hoi an", "hội an"]},
        {"id": "phu_quoc", "canonical_name": "phú quốc", "aliases": ["phu quoc", "phú quốc"]},
        {"id": "phan_thiet", "canonical_name": "phan thiết", "aliases": ["phan thiet", "phan thiết"]},
        {"id": "nha_trang", "canonical_name": "nha trang", "aliases": ["nha trang"]},
        {"id": "sapa", "canonical_name": "sapa", "aliases": ["sapa", "sa pa"]},
        {"id": "vung_tau", "canonical_name": "vũng tàu", "aliases": ["vung tau", "vũng tàu"]},
        {"id": "can_tho", "canonical_name": "cần thơ", "aliases": ["can tho", "cần thơ"]},
        {"id": "mui_ne", "canonical_name": "mũi né", "aliases": ["mui ne", "mũi né"]},
    ],
    "notes": "Small deterministic location reference for chat_api. Generic near-airport phrases are ignored unless a named airport alias appears.",
}


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(DATA_DIR / "supported_areas.json", SUPPORTED_AREAS)
    _write_json(DATA_DIR / "landmarks.json", LANDMARKS)
    _write_json(DATA_DIR / "location_rules.json", LOCATION_RULES)
    print(f"Wrote location reference JSON to {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
