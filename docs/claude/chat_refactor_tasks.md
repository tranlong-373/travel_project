# Chat Refactor — Implementation Guide

## Project Goal

Refactor `chat_api` để tách biệt "ý định tìm kiếm" (`SearchIntent`) khỏi logic parse thô, giúp `recommendation_bridge` nhận dữ liệu sạch hơn — không phải dict tùy tiện. Không viết lại hệ thống, chỉ thêm lớp DTO và adapter.

---

## Non-Goals (KHÔNG làm)

- Không đổi `recommendations/services.py` — recommendation engine giữ nguyên.
- Không đổi model: `Accommodation`, `UserPreference`, `PlaceReference`.
- Không thay bbox + haversine sang PostGIS, SpatiaLite, Pelias, Photon.
- Không migrate DB, không thêm migration.
- Không tối ưu data layer (bảng `AccommodationSearchIndex` để phase sau).
- Không làm lại NLU/NER, Groq LLM pipeline, slot extraction.

---

## Current Constraints (giữ nguyên backward compat)

| Điểm cần giữ | File | Ghi chú |
|---|---|---|
| `parse_user_text(text, *, locale, context_slots, include_debug)` | `parser_service.py:1541` | Signature không đổi, return dict không đổi |
| `create_preference_from_parse(parse_result)` | `recommendation_bridge.py:110` | Vẫn nhận dict, vẫn raise ValueError như cũ |
| `POST /api/chat/parse/` | `views.py → parse_message` | Response shape không đổi |
| `POST /api/chat/submit/` | `views.py → submit_message` | Response shape không đổi |
| `usable_filters_from_parse(parse_result)` | `recommendation_bridge.py:18` | Logic không đổi |
| `attach_recommendation_action(...)` | `recommendation_bridge.py:58` | Logic không đổi |

---

## Target Architecture

```
parse_user_text()          ← giữ nguyên, vẫn return dict
      │
      ▼
[SearchIntent DTO]         ← MỚI: dataclass trung tâm, typed
      │
      ▼
[SearchIntentAdapter]      ← MỚI: chuyển SearchIntent → dict shape cũ
      │
      ▼
create_preference_from_parse()   ← vẫn nhận dict (từ adapter)
      │
      ▼
recommendations/services.py      ← không đổi
```

**Luồng bên trong recommendation_bridge (nội bộ thôi):**

`create_preference_from_parse(dict)` → build `SearchIntent` → validate → build `UserPreference`

Public interface không đổi.

---

## Proposed File Layout

```
chat_api/
  intent/
    __init__.py
    search_intent.py        # SearchIntent dataclass + enums
    intent_builder.py       # build SearchIntent từ parse_result dict
    intent_adapter.py       # chuyển SearchIntent → dict (backward compat)
    intent_validator.py     # validate SearchIntent, raise ValueError chuẩn
```

File hiện tại `recommendation_bridge.py` sẽ dùng các module trên bên trong, public API không thay đổi.

---

## Phase 1 — SearchIntent DTO

### Task 1.1 — Định nghĩa SearchIntent dataclass

**File:** `chat_api/intent/search_intent.py`

```python
@dataclass
class SearchIntent:
    location_mode: str          # "area" | "near_anchor" | "near_user" | "anywhere" | "city_center"
    canonical_area: str | None
    anchor_lat: float | None
    anchor_lon: float | None
    accommodation_types: list[str]
    budget_min: int | None
    budget_max: int | None
    guest_count: int | None
    required_amenities: list[str]
    rating: float | None
    priorities: list[str]
    nearby_place: str | None
    conversation_intent: str
    can_show_recommendations: bool
    recommendation_level: str   # "none" | "low" | "high"
```

**Acceptance criteria:**
- [ ] Dataclass import được, không lỗi.
- [ ] Tất cả field có type annotation, có default hợp lý.
- [ ] Không kéo theo import từ Django hay DB.

---

### Task 1.2 — IntentBuilder: dict → SearchIntent

**File:** `chat_api/intent/intent_builder.py`

Build `SearchIntent` từ `parse_result` dict hiện tại. Tách hết logic đọc field lặp lại ra đây.

**Acceptance criteria:**
- [ ] `IntentBuilder.from_parse_result(parse_result: dict) -> SearchIntent` hoạt động.
- [ ] Các trường `anchor_lat/lon` đọc đúng từ cả `parse_result` lẫn `filter_tree.location`.
- [ ] Unit test: build từ fixture dict → SearchIntent đúng field.

---

### Task 1.3 — IntentValidator: validate SearchIntent

**File:** `chat_api/intent/intent_validator.py`

Chuyển toàn bộ logic `if not ... raise ValueError` trong `create_preference_from_parse` sang đây.

**Acceptance criteria:**
- [ ] `IntentValidator.validate(intent: SearchIntent) -> None` — raise `ValueError` đúng message như hiện tại.
- [ ] Các message lỗi giống hệt chuỗi hiện tại (để không break test đang mock).
- [ ] Unit test: validate intent hợp lệ pass, intent thiếu field raise ValueError đúng.

---

### Task 1.4 — IntentAdapter: SearchIntent → dict

**File:** `chat_api/intent/intent_adapter.py`

Chuyển `SearchIntent` ngược về dict với đúng shape mà `create_preference_from_parse` đang đọc — dùng trong trường hợp cần pass lại cho code cũ.

**Acceptance criteria:**
- [ ] `IntentAdapter.to_legacy_dict(intent: SearchIntent) -> dict` — output dict có đủ key.
- [ ] Round-trip test: dict → SearchIntent → dict → parse lại → kết quả bằng nhau.

---

## Phase 2 — Wiring vào recommendation_bridge

### Task 2.1 — Dùng SearchIntent bên trong create_preference_from_parse

Không đổi public API. Chỉ đổi phần thân hàm:

```python
def create_preference_from_parse(parse_result: dict) -> dict:
    intent = IntentBuilder.from_parse_result(parse_result)
    IntentValidator.validate(intent)          # raise ValueError như cũ
    # ... tiếp tục build UserPreference dùng intent.xxx thay vì dict lookup
```

**Acceptance criteria:**
- [ ] Tất cả test hiện tại trong `tests.py` vẫn pass.
- [ ] Không thay đổi response của `/api/chat/submit/`.
- [ ] Không thay đổi response của `/api/chat/parse/`.

---

### Task 2.2 — Dọn duplicate field reads

Sau khi có SearchIntent, xóa các đoạn đọc field lặp lại trực tiếp từ dict trong `recommendation_bridge.py` (các hàm `_read_user_location`, `_read_anchor_location`, `_read_search_origin_location` vẫn giữ — chỉ loại bỏ code đọc lặp).

**Acceptance criteria:**
- [ ] Không còn đoạn `parse_result.get("anchor_lat") or (filter_tree.get(...))` bị duplicate.
- [ ] Tất cả test pass.

---

## Test Checklist

Trước khi merge mỗi phase:

```
[ ] python manage.py test accommodation_project.chat_api     — all pass
[ ] POST /api/chat/parse/ với text "khách sạn quận 1"        — response shape không đổi
[ ] POST /api/chat/submit/ với parse_result hợp lệ          — pref_id trả về
[ ] POST /api/chat/submit/ với parse_result thiếu location  — lỗi 422 như cũ
[ ] Kiểm tra usable_filters_from_parse vẫn return đúng list
[ ] Kiểm tra attach_recommendation_action vẫn build action đúng
```

---

## Rollback Strategy

- Mỗi phase là 1 PR riêng.
- `intent/` là thư mục mới hoàn toàn — nếu phase 1 lỗi, xóa thư mục, không ảnh hưởng gì.
- Phase 2 chỉ đổi phần thân `create_preference_from_parse` — nếu test fail, revert commit phase 2, phase 1 vẫn sống.
- Không đụng `parser_service.py`, `views.py`, `recommendations/` → rollback nhanh.

---

## Final Verification Checklist

Sau khi hoàn thành cả 2 phase:

```
[ ] gitnexus_detect_changes() — chỉ thấy file trong chat_api/intent/ và recommendation_bridge.py
[ ] parse_user_text() signature không đổi
[ ] create_preference_from_parse() signature không đổi
[ ] Tất cả URL /api/chat/* response shape giống trước
[ ] Không có migration mới
[ ] Không import từ PostGIS/SpatiaLite/Pelias
[ ] recommendations/services.py không bị chạm
[ ] models.py (Accommodation, UserPreference, PlaceReference) không bị chạm
```
