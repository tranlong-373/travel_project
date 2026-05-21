# Chi Tiết PHASE 3 & PHASE 4

---

## PHASE 3 — Data HCM Mở Rộng (3 Tasks)

### **Task P3.1: Thêm 10 HCM Landmarks vào `landmarks.json`**

**Vấn đề hiện tại:**
- `landmarks.json` chỉ có 10 entries, trong đó chỉ có 10 là HCM (không chính xác — data cũ)
- Thiếu tọa độ `lat/lon` (chỉ có `name`, `aliases`, `parent_area_id`, `category`, `importance`)
- Thiếu nhiều landmark HCM nổi tiếng mà user hay search: Thảo Cầm Viên, Đầm Sen, Suối Tiên, etc.

**Hiện tại có:**
```json
[
  { "name": "Landmark 81", "aliases": [...], "parent_area_id": "tp_hcm", ... },
  { "name": "Bến Thành", "aliases": [...], "parent_area_id": "tp_hcm", ... },
  { "name": "Nhà thờ Đức Bà", ... },
  { "name": "Dinh Độc Lập", ... },
  { "name": "Tân Sơn Nhất", ... },
  { "name": "Chợ Rẫy", ... },
  { "name": "Hồ Con Rùa", ... },
  { "name": "Bến Nhà Rồng", ... },
  { "name": "Công viên Tao Đàn", ... },
  { "name": "Cầu Ánh Sao", ... }
]
```

**Thêm vào:**
```json
11. { 
  "name": "Thảo Cầm Viên", 
  "aliases": ["thao cam vien", "saigon zoo", "vung thu", "vuon thu"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7884, 
  "lon": 106.7060, 
  "radius_km": 2.0,
  "category": "attraction",
  "importance": 80
}

12. { 
  "name": "Đầm Sen", 
  "aliases": ["dam sen", "khu du lich dam sen", "tao dao"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7640, 
  "lon": 106.6397, 
  "radius_km": 3.0,
  "category": "amusement_park",
  "importance": 75
}

13. { 
  "name": "Suối Tiên", 
  "aliases": ["suoi tien", "khu vui choi suoi tien"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.8700, 
  "lon": 106.8031, 
  "radius_km": 5.0,
  "category": "amusement_park",
  "importance": 78
}

14. { 
  "name": "Bùi Viện", 
  "aliases": ["bui vien", "pho tay", "pho di bo bui vien", "backpacker street"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7691, 
  "lon": 106.6946, 
  "radius_km": 1.0,
  "category": "street",
  "importance": 85
}

15. { 
  "name": "Phú Mỹ Hưng", 
  "aliases": ["phu my hung", "phu my hung urban", "pmh"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7292, 
  "lon": 106.7032, 
  "radius_km": 3.5,
  "category": "urban_area",
  "importance": 80
}

16. { 
  "name": "Bitexco", 
  "aliases": ["bitexco", "toa nha bitexco", "bitexco financial tower"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7712, 
  "lon": 106.7038, 
  "radius_km": 1.5,
  "category": "landmark",
  "importance": 82
}

17. { 
  "name": "Bảo tàng Chứng tích Chiến tranh", 
  "aliases": ["bao tang chung tich chien tranh", "war remnants museum", "ctct"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7793, 
  "lon": 106.6921, 
  "radius_km": 1.5,
  "category": "museum",
  "importance": 78
}

18. { 
  "name": "Chợ Lớn", 
  "aliases": ["cho lon", "binh tay", "cho binh tay", "chinatown saigon", "cho lon"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.7553, 
  "lon": 106.6570, 
  "radius_km": 2.5,
  "category": "market",
  "importance": 80
}

19. { 
  "name": "Grand Park", 
  "aliases": ["grand park", "cong vien grand park", "vinhomes grand park"],
  "parent_area_id": "tp_hcm", 
  "lat": 10.8349, 
  "lon": 106.8210, 
  "radius_km": 4.0,
  "category": "park",
  "importance": 76
}

20. { 
  "name": "Địa đạo Củ Chi", 
  "aliases": ["dia dao cu chi", "cu chi tunnels", "cu chi"],
  "parent_area_id": "tp_hcm", 
  "lat": 11.0549, 
  "lon": 106.4670, 
  "radius_km": 5.0,
  "category": "historical",
  "importance": 75
}
```

**Lợi ích:**
- User nói "gần Thảo Cầm Viên" → chatbot tìm hotel trong bán kính 2km quanh tọa độ (10.7884, 106.7060)
- User nói "gần Suối Tiên" → radius 5km (vì ngoài thành phố)
- Không phải hỏi "Bạn muốn tìm ở đâu?" nữa

**File:** `chat_api/data/landmarks.json`

---

### **Task P3.2: Migrate HCM Districts từ Python → JSON**

**Vấn đề hiện tại:**
- `supported_areas.json` chỉ có 1 entry HCM (top-level city "tp_hcm" - không có tọa độ)
- HCM districts (Q1, Q2, Q3, ..., Q12, Thủ Đức, Bình Thạnh, etc.) nằm **hardcoded trong Python code**:
  - File: `chat_api/location_gazetteer.py` (dòng 30-45)
  - Function: `_FALLBACK_LOCATION_SPECS`
  - Chứa 23 entries cho HCM (12 quận + Thủ Đức + 10 huyện/quận ngoài)

**Hiện tại ở Python code:**
```python
# location_gazetteer.py:30-45
_FALLBACK_LOCATION_SPECS = [
    LocationSpec(
        name="TP. Hồ Chí Minh",
        aliases=["tp hcm", "tphcm", "sai gon"],
        lat=10.7769, lon=106.7009, radius_km=20.0
    ),
    LocationSpec(name="Quận 1", aliases=["q1", "quan 1"], lat=10.7710, lon=106.7021, radius_km=3.0),
    LocationSpec(name="Quận 3", aliases=["q3", "quan 3"], lat=10.7811, lon=106.6844, radius_km=3.0),
    ...
]
```

**Cần migrate vào JSON:**
```json
// supported_areas.json — thêm vào root array
{
  "id": "q1-hcm",
  "canonical_name": "Quận 1 (TP HCM)",
  "parent_id": "tp_hcm",
  "lat": 10.7710,
  "lon": 106.7021,
  "radius_km": 3.0,
  "supported": true,
  "type": "district",
  "aliases": ["q1", "quan 1", "quận 1", "district 1", "q.1", "q 1"]
},
{
  "id": "q3-hcm",
  "canonical_name": "Quận 3 (TP HCM)",
  "parent_id": "tp_hcm",
  "lat": 10.7811,
  "lon": 106.6844,
  "radius_km": 3.0,
  "supported": true,
  "type": "district",
  "aliases": ["q3", "quan 3", "quận 3", "district 3", "q.3"]
},
{
  "id": "thu-duc",
  "canonical_name": "Thủ Đức (TP HCM)",
  "parent_id": "tp_hcm",
  "lat": 10.8020,
  "lon": 106.7317,
  "radius_km": 5.0,
  "supported": true,
  "type": "district",
  "aliases": ["thủ đức", "thu duc", "td"]
},
{
  "id": "binh-thanh",
  "canonical_name": "Bình Thạnh (TP HCM)",
  "parent_id": "tp_hcm",
  "lat": 10.8059,
  "lon": 106.7140,
  "radius_km": 4.0,
  "supported": true,
  "type": "district",
  "aliases": ["bình thạnh", "binh thanh", "bt"]
},
// ... Q2, Q4–Q12, Gò Vấp, Tân Bình, Tân Phú, Phú Nhuận, Bình Chánh, Nhà Bè, Củ Chi, Cần Giờ, Hóc Môn
```

**Toàn bộ HCM districts cần add:**
```
Quận 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
Thủ Đức (city district — mới từ 2020)
Bình Thạnh, Gò Vấp, Tân Bình, Tân Phú, Phú Nhuận (inner districts)
Bình Chánh, Nhà Bè, Củ Chi, Cần Giờ (outer districts)
Hóc Môn (outer district)
```

**Cũng cần update:**
1. `supported_areas.json` — thêm `lat`, `lon`, `radius_km` vào entry "tp_hcm" (hiện không có)
2. `location_gazetteer.py` — sau khi migrate xong, không cần hardcode nữa, load từ JSON

**Lợi ích:**
- Dễ cập nhật: chỉ cần edit JSON, không cần thay code Python
- Có tọa độ chính xác cho từng quận
- Một source of truth (JSON)
- Có thể thêm trường mới (district_code, population, etc.) dễ dàng

**File:** `chat_api/data/supported_areas.json`, `chat_api/location_gazetteer.py`

**Tọa độ cần chuẩn bị (center + radius):**
```python
Q1: (10.7710, 106.7021), radius=3.0
Q2: (10.7520, 106.7570), radius=3.0
Q3: (10.7811, 106.6844), radius=3.0
Q4: (10.7420, 106.6734), radius=3.0
Q5: (10.7553, 106.6570), radius=3.5  # Chợ Lớn area
Q6: (10.7553, 106.6570), radius=3.5  # Overlaps with Q5
Q7: (10.7460, 106.7110), radius=3.5
Q8: (10.7300, 106.7380), radius=4.0
Q9: (10.7050, 106.7800), radius=4.5
Q10: (10.7650, 106.6300), radius=4.0
Q11: (10.6700, 106.6400), radius=4.5
Q12: (10.8480, 106.6570), radius=5.0
Thủ Đức: (10.8020, 106.7317), radius=5.0
Bình Thạnh: (10.8059, 106.7140), radius=4.0
Gò Vấp: (10.8350, 106.6650), radius=3.5
Tân Bình: (10.8140, 106.6600), radius=3.5
Tân Phú: (10.8400, 106.6200), radius=4.0
Phú Nhuận: (10.8150, 106.6850), radius=3.5
Bình Chánh: (10.6300, 106.5800), radius=8.0
Nhà Bè: (10.5300, 106.7400), radius=6.0
Củ Chi: (11.0650, 106.4200), radius=8.0
Cần Giờ: (10.3300, 106.9800), radius=10.0
Hóc Môn: (10.8780, 106.5700), radius=6.0
```

---

### **Task P3.3: Mở rộng `place_aliases.json`**

**Vấn đề hiện tại:**
- `place_aliases.json` chỉ có 13 entries
- Một số landmarks từ `landmarks.json` không có entry trong place_aliases → không resolve tốt khi user search

**Hiện tại có:**
```json
{
  "dinh doc lap": ["Dinh Độc Lập", ...],
  "dam sen": ["Đầm Sen", ...],
  "suoi tien": ["Suối Tiên", ...],
  "dia dao cu chi": ["Địa đạo Củ Chi", ...],
  "snow town sai gon": ["Snow Town", ...],
  "bui vien": ["Bùi Viện", ...],
  "thao cam vien": ["Thảo Cầm Viên", ...],
  "cho tan binh": ["Chợ Tân Bình", ...],
  "cho tan dinh": ["Chợ Tân Định", ...],
  "phu my hung": ["Phú Mỹ Hưng", ...],
  "cong vien grand park": ["Grand Park", ...],
  "noc ham thu thiem": ["Nóc hầm Thủ Thiêm", ...],
  "bao tang y hoc co truyen": ["Bảo tàng Y học cổ truyền", ...]
}
```

**Thêm vào (~6 entries):**
```json
{
  "khu cong nghe cao": [
    "Khu Công nghệ cao",
    "saigon hi-tech park",
    "shtp",
    "phan xi phuong"
  ]
},
{
  "pho di bo nguyen hue": [
    "Phố đi bộ Nguyễn Huệ",
    "walking street",
    "pho di bo"
  ]
},
{
  "cho an dong": [
    "Chợ An Đông",
    "cho an dong o p5 q5"
  ]
},
{
  "san van dong thong nhat": [
    "Sân vận động Thống Nhất",
    "thong nhat stadium",
    "thong nhat"
  ]
},
{
  "san bay long thanh": [
    "Sân bay Long Thành",
    "long thanh airport",
    "long thanh",
    "airport long thanh"
  ]
},
{
  "bitexco": [
    "Bitexco",
    "bitexco financial tower",
    "toa nha bitexco",
    "bitexco tower"
  ]
},
{
  "bao tang chung tich chien tranh": [
    "Bảo tàng Chứng tích Chiến tranh",
    "war remnants museum",
    "ctct",
    "war museum"
  ]
},
{
  "cho lon": [
    "Chợ Lớn",
    "binh tay",
    "cho binh tay",
    "chinatown saigon"
  ]
}
```

**Lợi ích:**
- Khi user nói "gần Khu Công nghệ cao" → resolve to coordinates
- Khi user nói "ở Chợ Lớn" hoặc "Bình Tây" → cùng một landmark
- Alias "SHTP" → full name "Khu Công nghệ cao"

**File:** `chat_api/data/place_aliases.json`

---

## PHASE 4 — Misc Fixes (3 Small Tasks)

### **Task P4.1: Locale "zh" (Chinese) Silent Fallback → Log Warning**

**Vấn đề:**
```python
# parser_service.py:356
def _normalize_locale(locale):
    locale = (locale or "vi").strip().lower()
    if locale not in ["vi", "en"]:
        locale = "vi"  # ← Silent fallback
    return locale
```

Khi user gửi `locale="zh"`, hệ thống im lặng đổi thành Vietnamese. Không log, không tell user.

**Fix:**
```python
def _normalize_locale(locale):
    locale = (locale or "vi").strip().lower()
    if locale not in ["vi", "en"]:
        logger.warning(f"Unsupported locale '{locale}', falling back to Vietnamese (vi)")
        locale = "vi"
    return locale
```

**Lợi ích:**
- DevOps/support biết có requests từ unsupported locales
- Có thể thêm support cho `en-US`, `vi-VN`, etc. sau khi thấy demand
- Transparent behavior

**File:** `chat_api/parser_service.py:356`

---

### **Task P4.2: Guest Count > 30 Bị Drop Silent → Cap at 30**

**Vấn đề:**
```python
# slot_validator.py:145
guest_count = _as_int(slots.get("guest_count"))
slots["guest_count"] = guest_count if guest_count is not None and 1 <= guest_count <= 30 else None
                       # ↑ Nếu guest_count=200, nó bị set thành None
```

User nói "khách sạn cho 200 người" → extract được 200 → nhưng nhét vào DB để search → filter "capacity >= 200" → 0 results → user confused.

**Fix:**
```python
# slot_validator.py:145
guest_count = _as_int(slots.get("guest_count"))
if guest_count is not None and guest_count >= 1:
    slots["guest_count"] = min(guest_count, 30)  # ← Cap at 30, don't drop to None
else:
    slots["guest_count"] = None
```

**Lợi ích:**
- User nói "200 người" → system searches for "capacity >= 30" (max available)
- Không bị confusion, explicit cap thay vì silent drop
- Phù hợp hơn cho group bookings

**File:** `chat_api/slot_validator.py:145`

---

### **Task P4.3: Trip Days > 365 Bị Drop Silent → Cap at 365**

**Vấn đề:**
```python
# slot_validator.py:148
trip_days = _as_int(slots.get("trip_days"))
slots["trip_days"] = trip_days if trip_days is not None and 1 <= trip_days <= 365 else None
                    # ↑ Nếu trip_days=600, nó bị set thành None (long-term stays lost)
```

User nói "ở 600 ngày" (18+ months) → extract được 600 → drop to None → recommendation không có duration constraint → wrong results.

**Fix:**
```python
# slot_validator.py:148
trip_days = _as_int(slots.get("trip_days"))
if trip_days is not None and trip_days >= 1:
    slots["trip_days"] = min(trip_days, 365)  # ← Cap at 365, don't drop
else:
    slots["trip_days"] = None
```

**Lợi ích:**
- User nói "ở 600 ngày" → search for 365 days (max available, not 0 days)
- Better than silent drop
- Long-term rental searches don't get confused

**File:** `chat_api/slot_validator.py:148`

---

## Tóm Tắt P3 & P4

| Task | What | Why | Effort | Files |
|---|---|---|---|---|
| **P3.1** | Add 10 HCM landmarks with lat/lon | User can search "gần Thảo Cầm Viên" | 1h | `landmarks.json` |
| **P3.2** | Move Q1-Q12 districts from Python → JSON | Easier to maintain, one source of truth | 2h | `supported_areas.json`, `location_gazetteer.py` |
| **P3.3** | Expand place_aliases with 6 more HCM spots | Better place resolution | 30m | `place_aliases.json` |
| **P4.1** | Log locale warning instead of silent fallback | Observable behavior, track unsupported locales | 5m | `parser_service.py` |
| **P4.2** | Cap guest_count at 30 instead of dropping | User expectations met (get some results) | 5m | `slot_validator.py` |
| **P4.3** | Cap trip_days at 365 instead of dropping | Long-term rentals don't get confusing results | 5m | `slot_validator.py` |

---

## Thực Hiện P3 & P4

**Recommended order:**
1. P3.2 trước (JSON update — dùng được ngay)
2. P3.1 & P3.3 cùng (cùng data files)
3. P4.1, P4.2, P4.3 cùng (cùng Python code)

**Impact level:**
- P3 = HIGH (data expand, HCM coverage +100%)
- P4 = MEDIUM (edge case handling, better UX)

**Risk level:**
- P3.1, P3.3 = Zero (append-only)
- P3.2 = Low (migration, but need testing)
- P4 = Zero (simple logic changes)

