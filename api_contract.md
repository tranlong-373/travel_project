# API Contract

Tài liệu này mô tả contract hiện tại giữa frontend, `chat_api`, `preferences` và `recommendations`.

## Flow API

```text
User nhập text
-> POST /api/chat/parse/
-> nếu thiếu core slot: dùng follow_up_question để hỏi tiếp
-> nếu đủ dữ liệu: POST /api/chat/submit/
-> nhận pref_id + recommendation_url
-> GET /recommendations/<pref_id>/
```

`chat_api` không gọi thuật toán recommendation trực tiếp. Nó parse text thành slots và tạo `UserPreference` khi dữ liệu đủ an toàn. `recommendations` đọc `UserPreference` qua `pref_id`.

## Health

```http
GET /api/chat/health/
```

Response mẫu:

```json
{
  "status": "ok",
  "service": "chat_api",
  "parser_mode": "deterministic_fast",
  "use_ner_fallback": false
}
```

## Parse Only

```http
POST /api/chat/parse/
Content-Type: application/json
```

Request:

```json
{
  "text": "Khách sạn ở Sài Gòn cho 2 người, budget 900k, có wifi",
  "locale": "vi"
}
```

`locale` optional. Giá trị hợp lệ hiện tại: `vi`, `en`. Nếu không gửi hoặc gửi giá trị khác, server dùng `vi`.

Response mẫu khi đủ dữ liệu:

```json
{
  "schema_version": "1.1",
  "intent": "recommend_accommodation",
  "slots": {
    "area": "tp hcm",
    "budget": 900000,
    "guest_count": 2,
    "preferred_type": "hotel",
    "required_amenities": ["wifi"],
    "priorities": [],
    "special_requirements": [],
    "trip_days": null
  },
  "missing_slots": [],
  "suggested_questions": [],
  "ready_for_recommendation": true,
  "should_ask_optional": false,
  "follow_up_question": null,
  "parser_mode": "deterministic_fast",
  "location_status": "ok",
  "location_candidates": [],
  "canonical_area": "tp hcm"
}
```

Response mẫu khi thiếu dữ liệu:

```json
{
  "schema_version": "1.1",
  "intent": "recommend_accommodation",
  "slots": {
    "area": "hà nội",
    "budget": null,
    "guest_count": 2,
    "preferred_type": "hotel",
    "required_amenities": [],
    "priorities": [],
    "special_requirements": [],
    "trip_days": null
  },
  "missing_slots": ["budget"],
  "suggested_questions": ["Ngân sách tối đa của bạn khoảng bao nhiêu VND/đêm?"],
  "ready_for_recommendation": false,
  "should_ask_optional": false,
  "follow_up_question": "Ngân sách tối đa của bạn khoảng bao nhiêu VND/đêm?",
  "parser_mode": "deterministic_fast",
  "location_status": "ok",
  "location_candidates": [],
  "canonical_area": "hà nội"
}
```

Parse endpoint không tạo `UserPreference`.

## Submit

```http
POST /api/chat/submit/
Content-Type: application/json
```

Request giống `/parse/`:

```json
{
  "text": "Khách sạn ở Sài Gòn cho 2 người, budget 900k, có wifi",
  "locale": "vi"
}
```

Nếu đủ dữ liệu, response status hiện tại là `201`:

```json
{
  "schema_version": "1.1",
  "intent": "recommend_accommodation",
  "slots": {
    "area": "tp hcm",
    "budget": 900000,
    "guest_count": 2,
    "preferred_type": "hotel",
    "required_amenities": ["wifi"],
    "priorities": [],
    "special_requirements": [],
    "trip_days": null
  },
  "missing_slots": [],
  "suggested_questions": [],
  "ready_for_recommendation": true,
  "should_ask_optional": false,
  "follow_up_question": null,
  "parser_mode": "deterministic_fast",
  "location_status": "ok",
  "location_candidates": [],
  "canonical_area": "tp hcm",
  "created_preference": true,
  "pref_id": 1,
  "recommendation_url": "/recommendations/1/"
}
```

Nếu thiếu dữ liệu, response status hiện tại là `200` và không tạo DB record:

```json
{
  "ready_for_recommendation": false,
  "created_preference": false,
  "pref_id": null,
  "recommendation_url": null,
  "follow_up_question": "Ngân sách tối đa của bạn khoảng bao nhiêu VND/đêm?"
}
```

## Recommendation

```http
GET /recommendations/<pref_id>/
```

Endpoint này đọc `UserPreference` theo `pref_id`, lấy `Accommodation`, tính score và render template HTML `recommendations/recommendation_result.html`.

Hiện endpoint này không trả JSON.

## Context Cho Hội Thoại Nhiều Lượt

Khi user trả lời thiếu một phần, frontend nên gửi lại `context_slots` từ response trước đó.

Lượt 1:

```json
{
  "text": "Khách sạn ở Hà Nội cho 2 người"
}
```

Lượt 2:

```json
{
  "text": "900k",
  "context_slots": {
    "area": "hà nội",
    "budget": null,
    "guest_count": 2,
    "preferred_type": "hotel",
    "required_amenities": [],
    "priorities": [],
    "special_requirements": [],
    "trip_days": null
  }
}
```

## Field Quan Trọng

- `slots.area`: khu vực canonical dùng để tạo `UserPreference.area`.
- `slots.budget`: số nguyên VND mỗi đêm.
- `slots.guest_count`: số khách là người, không tính chó/mèo/pet.
- `slots.preferred_type`: optional. Có thể là `null`.
- `slots.required_amenities`: list key canonical.
- `missing_slots`: core slots còn thiếu.
- `ready_for_recommendation`: chỉ true khi đủ core slots và location hợp lệ.
- `follow_up_question`: câu frontend nên hỏi tiếp user.
- `location_status`: trạng thái resolve địa điểm.
- `pref_id`: ID `UserPreference` mới tạo từ `/submit/`.
- `recommendation_url`: route hiện tại để lấy trang kết quả recommendation.

## Location Status

- `ok`: resolve được một khu vực được hỗ trợ.
- `multiple_choice`: user nêu nhiều khu vực được hỗ trợ theo kiểu lựa chọn.
- `conflict`: user nêu nhiều địa điểm mâu thuẫn.
- `unsupported`: địa điểm nhận diện được nhưng ngoài phạm vi hỗ trợ.
- `unresolved`: chưa nhận diện được địa điểm.

Chỉ gọi recommendation khi:

```text
ready_for_recommendation = true
location_status = "ok"
pref_id != null
```

## Enum Hiện Tại

Supported recommendation areas trong `chat_api`:

- `tp hcm`
- `hà nội`
- `thanh hóa`
- `đồng nai`
- `an giang`
- `bình định`

Allowed `preferred_type`:

- `hotel`
- `homestay`
- `hostel`
- `apartment`

`resort` hiện được nhận diện là unsupported type candidate nhưng không bật thành `preferred_type`, vì model downstream chưa có type này.

Allowed `required_amenities` từ parser:

- `wifi`
- `pool`
- `parking`
- `air_conditioner`
- `breakfast`
- `balcony`
- `bathtub`
- `kitchen`
- `washing_machine`

Allowed `priorities`:

- `near_center`
- `near_beach`
- `cheap`
- `quiet`
- `high_rating`
- `nice_view`

Allowed `special_requirements`:

- `baby_friendly`
- `elderly_friendly`
- `pet_friendly`
- `work_friendly`
- `private`
- `safe_area`

Hiện `priorities`, `special_requirements`, `trip_days` chưa được lưu vào `UserPreference` và chưa được recommender dùng trực tiếp.

## Error Response

Các lỗi cơ bản hiện tại:

```json
{"error": "Only POST allowed"}
```

```json
{"error": "Invalid JSON"}
```

```json
{"error": "JSON body must be an object"}
```

```json
{"error": "Field 'text' is required"}
```
