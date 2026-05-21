# Báo Cáo Phân Tích Chi Tiết - Chatbot Tìm Kiếm Chỗ Ở

## 📊 Tổng Quan Quy Trình

Chatbot nhận **text lọc từ người dùng** → xử lý NLU extraction → trích xuất các **slots (khe cắm)** → ánh xạ tới **kinh độ/vĩ độ** → trả về kết quả với filters và recommendations.

---

## 🏗️ Kiến Trúc Tổng Quan

```
┌─────────────────┐
│  User Input     │ (Text)
│  "Tìm hotel     │
│   ở Q1, 100k,   │
│   3 người"      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│            API ENDPOINTS (views.py)                  │
│                                                      │
│  • /api/parse_message - Parse only (tạm xử lý)      │
│  • /api/submit_message - Parse + Create preference  │
│  • /api/suggestions - Autocomplete địa điểm         │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│           PARSER SERVICE (parser_service.py)         │
│                                                      │
│  parse_user_text(text, locale, context_slots)       │
│  └─ Hybrid Pipeline (Rule-based + LLM)              │
└────────┬────────────────────────────────────────────┘
         │
         ▼ (Detailed flow below)
   [5 BUCKETS PROCESSING]
```

---

## 🪣 5 "BUCKETS" (BỘ XỬ LÝ CHÍNH) CỦA CHATBOT

### **BUCKET 1: INPUT NORMALIZATION & CLASSIFICATION**
**File:** `text_normalizer.py`, `input_classifier.py`, `domain_router.py`

**Mục tiêu:** Làm sạch và phân loại ý định người dùng

**Chi tiết:**
- Chuẩn hóa text (remove diacritics, convert to lowercase, chuẩn hóa spacing)
- Xác định **intent** của người dùng:
  - `greeting` - Chào hỏi ("chào", "hi")
  - `thanks` - Cảm ơn ("cảm ơn", "thanks")
  - `search` - Tìm kiếm chỗ ở (intent chính)
  - `off_topic` - Ngoài phạm vi ("trời mưa", "bao nhiêu tuổi bạn")
  - `unknown` - Không xác định được

**Ví dụ:**
```
Input: "Tìm khách sạn ở Q1 cho 3 người, budget 100k"
→ Normalized: "tim khach san o q1 cho 3 nguoi budget 100k"
→ Intent: "search"
```

---

### **BUCKET 2: SLOT EXTRACTION (Trích xuất thông tin khóa)**
**File:** `slot_pipeline.py`, `slot_validator.py`, `extractors.py`

**Mục tiêu:** Tách các thành phần thông tin từ text

**Core Slots (8 thông tin cốt lõi):**
1. **area** - Khu vực (tỉnh/quận)
2. **budget** - Ngân sách (budget_min, budget_max, budget)
3. **guest_count** - Số lượng khách
4. **trip_days** - Số ngày ở
5. **preferred_type** - Loại chỗ ở (hotel, homestay, hostel, apartment, resort, villa)
6. **required_amenities** - Tiện nghi bắt buộc (wifi, pool, parking, kitchen, etc.)
7. **priorities** - Ưu tiên (high_rating, cheap, near_center, near_beach, etc.)
8. **special_requirements** - Yêu cầu đặc biệt (baby_friendly, pet_friendly, work_friendly)

**Cơ chế trích xuất:**

```python
# Type aliases (Type standardization)
TYPE_ALIASES = {
    "khách sạn", "khach san", "ks" → "hotel"
    "homestay", "home stay", "homstay" → "homestay"
    "nhà trọ", "nha tro", "phòng trọ" → "hostel"
    "căn hộ", "can ho", "apartment" → "apartment"
}

# Amenity aliases
AMENITY_ALIASES = {
    "parking", "đậu xe", "gửi xe", "gara" → "parking"
    "wifi", "mạng", "internet" → "wifi"
    "hồ bơi", "bể bơi", "swimming pool" → "pool"
    "bếp", "kitchen" → "kitchen"
}

# Budget patterns
"100k", "1.2tr", "150 nghin", "500 đô" → Extract & normalize to VND
```

**Ví dụ trích xuất:**
```
Input: "Tìm khách sạn ở Q1 cho 3 người, 100k/đêm, có wifi và hồ bơi"

Extracted slots:
{
    "area": "Q1",
    "preferred_type": ["hotel"],
    "guest_count": 3,
    "budget": 100000,
    "required_amenities": ["wifi", "pool"],
    "priorities": [],
    "special_requirements": [],
    "trip_days": None (not mentioned)
}
```

---

### **BUCKET 3: LOCATION RESOLUTION (Chuyển địa điểm → Lat/Lon)**
**File:** `location_resolver.py`, `location_gazetteer.py`, `nominatim_geocoder.py`, `fuzzy_location.py`

**Mục tiêu:** Convert text địa điểm sang tọa độ (latitude, longitude)

**3 cấp độ Resolution:**

#### **Level 1: Gazetteer Lookup (Tra cứu từ điển)**
- Load từ `data/supported_areas.json`, `data/landmarks.json`
- Chứa ~1000+ areas (tỉnh/quận) + ~500 landmarks (điểm tham quan)
- **Supported areas:** TP HCM, Hà Nội, Thanh Hóa, Đồng Nai, An Giang, Bình Định

```json
// Example from supported_areas.json
{
    "id": "q1-hcm",
    "canonical_name": "Quận 1 (TP HCM)",
    "parent_id": null,
    "aliases": ["q1", "quan 1", "district 1", "quận 1"],
    "lat": 10.7710,
    "lon": 106.7021,
    "default_radius_km": 3.0,
    "supported": true
}

// Example from landmarks.json
{
    "name": "Nhà thờ Đức Bà",
    "aliases": ["nha tho duc ba", "notre dame"],
    "parent_area_id": "q1-hcm",
    "lat": 10.7798,
    "lon": 106.6990,
    "importance": 95
}
```

#### **Location Resolution Logic:**

```
extract_location_mentions(text)
    ↓
Normalize text → "tim khach san o q1..."
    ↓
Search aliases using regex matching
    ↓
Multiple mentions? 
    → Single area? → status: "ok" → return coords
    → Multiple areas? → status: "conflict" → ask user to pick
    → Unsupported areas? → status: "unsupported" → suggest alternatives
    ↓
No mentions?
    → Try Nominatim geocoder (OSM API) for street addresses
    ↓
Can't resolve?
    → status: "unresolved" → ask follow-up question
```

**Ví dụ Resolution:**

```
Input: "Tìm ở Quận 1"
↓
extract_location_mentions("tim o quan 1")
↓
Found: [{
    "matched_text": "quan 1",
    "area_id": "q1-hcm",
    "canonical_area": "Quận 1 (TP HCM)",
    "supported": true,
    "lat": 10.7710,
    "lon": 106.7021,
    "default_radius_km": 3.0
}]
↓
Location Status: "ok"
Anchor Point: (10.7710, 106.7021) ← dùng để search hotels gần vị trí này
```

**Các Location Status Khác:**
```
"conflict"    - Nhiều area, không rõ ý muốn (Q1 vs Q3)
"multiple_choice" - Nhân dân nói "hoặc" (Q1 hoặc Q2)
"unsupported" - Đề cập địa điểm ngoài hỗ trợ (Đà Lạt)
"geocoded"    - Resolve bằng Nominatim (đường cụ thể)
"unresolved"  - Không tìm thấy địa điểm nào
```

---

### **BUCKET 4: FILTER TREE BUILDING (Xây dựng cây filters)**
**File:** `filter_tree.py`, `convenience_policy.py`

**Mục tiêu:** Tạo structured query filters cho recommendation engine

**Filter Node Structure:**
```python
@dataclass
class FilterNode:
    key: str              # "price_min", "accommodation_type"
    value: Any            # 100000, ["hotel", "hostel"]
    operator: str         # ">=", "in", "=="
    strength: FilterStrength  # "hard" (must have) vs "soft" (nice to have)
    confidence: float     # 1.0 (100% sure) to 0.5 (guess)
    priority: FilterPriority  # "must_have", "important", "nice_to_have"
    source: str          # "text_extraction", "user_confirmation"
    reason: str          # "user_explicit_mention", "fuzzy_match"
```

**Filter Examples:**
```
Input slots:
{
    "area": "Q1",
    "guest_count": 3,
    "budget": 100000,
    "preferred_type": ["hotel"],
    "required_amenities": ["wifi", "pool"]
}

↓ Build filter tree

Filters array:
[
    {
        "key": "location",
        "value": {"lat": 10.7710, "lon": 106.7021, "radius_km": 3.0},
        "operator": "near",
        "strength": "hard",
        "priority": "must_have"
    },
    {
        "key": "accommodation_type",
        "value": ["hotel"],
        "operator": "in",
        "strength": "hard",
        "priority": "must_have"
    },
    {
        "key": "price_max",
        "value": 100000,
        "operator": "<=",
        "strength": "hard",
        "priority": "important"
    },
    {
        "key": "amenities",
        "value": ["wifi", "pool"],
        "operator": "contains_all",
        "strength": "soft",
        "priority": "nice_to_have"
    },
    {
        "key": "capacity",
        "value": 3,
        "operator": ">=",
        "strength": "soft",
        "priority": "important"
    }
]
```

**FilterTree Contains:**
- **location** - Tọa độ anchor point + radius search
- **filters** - Array of FilterNode
- **available_slots** - Slots có giá trị ("area", "budget", "guest_count")
- **missing_slots** - Slots cần hỏi để có đủ info ("trip_days")
- **partial_intent** - True nếu chưa đủ info để tìm kiếm đầy đủ

---

### **BUCKET 5: RESPONSE GENERATION & INTENT DECISION**
**File:** `response_generator.py`, `response_templates.py`, `convenience_policy.py`, `smart_suggestions.py`

**Mục tiêu:** Quyết định phản hồi và hành động tiếp theo

**Response Types:**

#### **1. Terminal Responses (Kết thúc cuộc hội thoại)**
```
Greeting → "Chào bạn! Tôi có thể giúp bạn tìm chỗ ở. Bạn muốn tìm ở đâu?"
Thanks → "Không có chi! Hẹn gặp lại bạn."
Off-topic → "Mình chỉ hỗ trợ tìm kiếm chỗ ở. Bạn cần tìm khách sạn không?"
```

#### **2. Clarification Responses (Yêu cầu rõ ràng)**
```
Conflict (multiple areas):
{
    "follow_up_question": "Bạn muốn tìm ở Quận 1 hay Quận 3?",
    "location_candidates": [
        {"area_id": "q1-hcm", "canonical_area": "Quận 1 (TP HCM)"},
        {"area_id": "q3-hcm", "canonical_area": "Quận 3 (TP HCM)"}
    ]
}

Missing core slot:
{
    "follow_up_question": "Bạn muốn ở bao lâu?",
    "awaiting_confirmation": true,
    "missing_slots": ["trip_days"]
}
```

#### **3. Ready for Recommendation**
```
Conditions:
✓ Có ít nhất 1 core slot (area hoặc khác)
✓ Location resolved (status: "ok" hoặc "geocoded")
✓ Enough info to make query

Response:
{
    "ready_for_recommendation": true,
    "can_show_recommendations": true,
    "slots": { ... },
    "filter_tree": { ... },
    "partial_intent": false,
    "recommendation_url": "/recommendations?pref_id=12345"
}
```

**Decision Tree:**
```
Is this intent terminal?
├─ YES → Return greeting/thanks/off-topic response
└─ NO → Extract slots
        ├─ Location conflict?
        │  └─ YES → Ask which area
        ├─ Missing core info?
        │  └─ YES → Ask for info (budget, people count, days)
        └─ Ready to search?
           └─ YES → Create preference + return filters
```

---

## 🔄 FULL PIPELINE EXAMPLE

### **User says:** "Tìm hotel ở Q1 cho 3 người, budget 100k, có wifi"

```
STEP 1: INPUT NORMALIZATION (BUCKET 1)
─────────────────────────────────────
Input: "Tìm hotel ở Q1 cho 3 người, budget 100k, có wifi"
↓
Normalized: "tim hotel o q1 cho 3 nguoi budget 100k co wifi"
Intent classification: "search"
Domain: "accommodation_search"
```

```
STEP 2: SLOT EXTRACTION (BUCKET 2)
─────────────────────────────────────
Extract from normalized text:
• "hotel" → preferred_type: ["hotel"]
• "3 người" → guest_count: 3
• "100k" → budget: 100000
• "wifi" → required_amenities: ["wifi"]
• Area mentioned but not yet resolved
```

```
STEP 3: LOCATION RESOLUTION (BUCKET 3)
─────────────────────────────────────
Text: "ở Q1"
↓
Gazetteer lookup: "q1" → match found
↓
Result:
{
    "location_status": "ok",
    "canonical_area": "Quận 1 (TP HCM)",
    "anchor_lat": 10.7710,
    "anchor_lon": 106.7021,
    "location_mode": "area",
    "search_radius_km": 3.0,
    "matched_text": "q1"
}
```

```
STEP 4: FILTER TREE BUILDING (BUCKET 4)
─────────────────────────────────────
Combine slots + location:
{
    "filters": [
        {key: "accommodation_type", value: ["hotel"], strength: "hard"},
        {key: "amenities", value: ["wifi"], strength: "soft"},
        {key: "price_max", value: 100000, strength: "hard"},
        {key: "capacity", value: 3, strength: "soft"}
    ],
    "location": {
        "lat": 10.7710,
        "lon": 106.7021,
        "radius_km": 3.0,
        "mode": "area"
    },
    "available_slots": ["area", "guest_count", "budget", "required_amenities"],
    "missing_slots": ["trip_days"],
    "partial_intent": true  // trip_days missing
}
```

```
STEP 5: RESPONSE GENERATION (BUCKET 5)
─────────────────────────────────────
Check readiness:
• has location? YES (Q1)
• has budget? YES (100k)
• missing core? YES (trip_days)

Decision: Ask follow-up question

Response:
{
    "intent": "search",
    "ready_for_recommendation": false,
    "can_show_recommendations": false,
    "awaiting_confirmation": false,
    "follow_up_question": "Bạn muốn ở bao lâu?",
    "slots": {
        "area": "Quận 1 (TP HCM)",
        "preferred_type": ["hotel"],
        "guest_count": 3,
        "budget": 100000,
        "required_amenities": ["wifi"]
    },
    "filter_tree": { ... },
    "missing_slots": ["trip_days"],
    "suggested_questions": [
        "1 đêm",
        "2-3 đêm",
        "1 tuần"
    ]
}
```

```
User replies: "3 đêm"

STEP 2 again (with context):
────────────────────────────
Extract: "3 đêm" → trip_days: 3
Merge with context: {...existing slots..., trip_days: 3}

STEP 4-5: Filter tree updated
────────────────────────────
missing_slots: [] ✓ (all core slots filled)
partial_intent: false

Response:
{
    "ready_for_recommendation": true,
    "can_show_recommendations": true,
    "created_preference": true,
    "pref_id": "pref_xyz123",
    "recommendation_url": "/api/recommendations?pref_id=pref_xyz123",
    ...
}
```

---

## 🧠 LLM ENRICHMENT (Optional - Groq Integration)

**File:** `groq_llm.py`

**Khi nào gọi:**
- Rule-based extraction không tìm thấy `area` (vị trí quan trọng nhất)
- Groq API key có sẵn

**Groq làm gì:**
```python
# Input
text = "Tìm chỗ gần như Bến Thành"
context_slots = {} # Rule-based found nothing

# Groq call
groq_slots = groq_extract_slots(text, context_slots)
# Returns:
{
    "nearby_place": "Bến Thành",  # ← identify landmark
    "location_mode": "near_anchor"
}

# Merge with rule-based result
enriched = merge_groq_slots(rule_based_slots, groq_slots)
```

---

## 📊 Data Files Structure

```
chat_api/data/
├── supported_areas.json      # 1000+ areas (TP HCM, HN, etc.)
│   └── [{id, canonical_name, aliases, lat, lon, ...}]
├── landmarks.json            # 500+ POIs (attractions, hospitals, etc.)
│   └── [{name, aliases, parent_area_id, lat, lon, importance}]
├── location_rules.json       # Rules for conflict resolution
│   ├── unsupported_areas: Đà Lạt, Phú Quốc, etc.
│   └── multiple_choice_phrases: "hoặc", "hay là"
├── vietnamese_admin_units.json # Province/district tree
├── place_aliases.json        # Common place name variations
└── suggestion_catalog.json   # For autocomplete
```

---

## 🎯 Confidence & Quality Metrics

### **Location Confidence:**
```python
location_confidence = {
    "ok": 1.0,              # Perfect match
    "geocoded": 0.9,        # Nominatim resolved
    "conflict": 0.5,        # Multiple matches, ask user
    "unresolved": 0.0       # No match found
}
```

### **Filter Strength:**
```
"hard"   - Must be in database (location, type)
"soft"   - Nice to have but flexible (amenities)
"preference" - Ranking priority (high_rating)
"none"   - Informational only
```

---

## 🔗 Coordinate System

**Search Origin Types:**
```python
search_origin = {
    "type": "area_center",     # Search around area center
    "lat": 10.7710,
    "lon": 106.7021,
    "radius_km": 3.0,
    
    # OR
    
    "type": "landmark",        # Search near landmark
    "lat": 10.7798,
    "lon": 106.6990,
    "radius_km": 2.5,
    
    # OR
    
    "type": "address",         # Search near specific address
    "lat": 10.76,
    "lon": 106.68,
    "radius_km": 1.0
}
```

**Default radius_km by type:**
- City/Province: 3-10 km
- District: 3 km
- Landmark: 2-5 km
- Street address: 1 km

---

## 🚀 API Response Schema

### **parse_message endpoint** (Parse only)
```json
{
    "schema_version": "v2.3.1",
    "intent": "search",
    "conversation_intent": "search",
    "slots": {
        "area": "Quận 1 (TP HCM)",
        "preferred_type": ["hotel"],
        "guest_count": 3,
        "budget": 100000,
        "required_amenities": ["wifi"],
        "trip_days": null
    },
    "filter_tree": {
        "location": {...},
        "filters": [...],
        "available_slots": [...],
        "missing_slots": ["trip_days"],
        "partial_intent": true
    },
    "missing_slots": ["trip_days"],
    "ready_for_recommendation": false,
    "can_show_recommendations": false,
    "follow_up_question": "Bạn muốn ở bao lâu?",
    "location_status": "ok",
    "canonical_area": "Quận 1 (TP HCM)",
    "anchor_lat": 10.7710,
    "anchor_lon": 106.7021,
    "location_display_label": "Quận 1 (TP HCM)",
    "parser_mode": "hybrid_hf_transformers"
}
```

### **submit_message endpoint** (Parse + Create preference)
```json
{
    ...all fields from parse_message...
    "created_preference": true,        // ← NEW
    "pref_id": "pref_abc123",         // ← NEW
    "recommendation_url": "/api/recommendations?pref_id=pref_abc123"  // ← NEW
}
```

---

## 📈 Error Handling & Fallbacks

**Graceful degradation:**
```
LLM unavailable → Fall back to rule-based
Rule-based fails → Return generic response
Nominatim times out → Use gazetteer only
Groq API fails → Continue with rule-based (silent)
```

**Status codes:**
```
200 - Parsed successfully
201 - Parsed + preference created
400 - Missing required field (text)
405 - Wrong HTTP method
503 - Parser temporarily unavailable
```

---

## 🎓 Summary: Request Flow Chart

```
                         ┌─────────────────┐
                         │   User Input    │
                         └────────┬────────┘
                                  │
                    ┌─────────────▼────────────────┐
                    │  Normalize & Classify Intent │
                    │   (BUCKET 1)                 │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼─────────┐
                    │  Extract Slots     │
                    │  (BUCKET 2)        │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │  Resolve Location Mentions  │
                    │  → Lat/Lon (BUCKET 3)       │
                    └──────────┬──────────────────┘
                               │
                    ┌──────────▼────────────────┐
                    │  Build Filter Tree        │
                    │  (BUCKET 4)               │
                    └──────────┬────────────────┘
                               │
                    ┌──────────▼──────────────────────┐
                    │  Generate Response & Decision   │
                    │  (BUCKET 5)                     │
                    └──────────┬──────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   Terminal?            Clarify needed?         Ready to search?
    │                        │                       │
    ▼                        ▼                       ▼
 Response              Ask follow-up          Create preference
(greeting/              (conflict/            + return filters
 thanks)             missing slots)            for recommendations

```

---

## 🔍 Debugging Tips

### **Enable debug mode:**
```python
# In request body
{
    "text": "Tìm hotel ở Q1",
    "debug": true
}

# Returns debug_metadata with:
{
    "debug_metadata": {
        "raw_text": "Tìm hotel ở Q1",
        "normalized_text": "tim hotel o q1",
        "protected_spans": [],
        "location_candidate": "q1",
        "location_confidence": 1.0,
        "geocoder_called": false,
        "location_source": "gazetteer",
        "cache_hit": false,
        "area_match": true
    }
}
```

### **Check which model is used:**
```python
# GET /api/health
{
    "parser_mode": "hybrid_hf_transformers",
    "light_model": "Qwen/Qwen2.5-0.5B-Instruct",
    "model": "Qwen/Qwen2.5-1.5B-Instruct",
    "fallback_model": "...",
    "llm_strategy": "auto"  // or "never", "always"
}
```

---

## 📝 Key Files Reference

| File | Purpose |
|------|---------|
| `views.py` | API endpoints |
| `parser_service.py` | Main parsing orchestration |
| `text_normalizer.py` | Text cleaning |
| `input_classifier.py` | Intent detection |
| `slot_pipeline.py` | Slot extraction |
| `location_resolver.py` | Location → Coordinates |
| `filter_tree.py` | Build structured filters |
| `response_generator.py` | Response decision logic |
| `response_templates.py` | Response text templates |
| `groq_llm.py` | LLM enrichment (optional) |
| `data/` | JSON reference data |

---

## 📌 Conclusion

**Chatbot quy trình 5 giai đoạn:**
1. **Normalize input** → Hiểu ý người dùng
2. **Extract slots** → Tách thông tin cốt lõi
3. **Resolve location** → Chuyển text thành lat/lon
4. **Build filters** → Tạo query structured
5. **Generate response** → Quyết định hành động (ask more / search / recommend)

**Kết quả cuối:** `{slots, filter_tree, recommendation_url}` → gửi sang recommendation engine để tìm khách sạn phù hợp
