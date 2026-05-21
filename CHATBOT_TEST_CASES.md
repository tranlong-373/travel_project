# Test Cases - Reproduce Chatbot Errors

## 🧪 How to Test

```bash
# Terminal 1: Run server
cd /home/thien_long/travel_project/travel_project/accommodation_project
python manage.py runserver

# Terminal 2: Run test
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "debug": true}' \
  | python -m json.tool
```

---

## ❌ Test Cases By Error Type

### **ERROR 1: Unresolved Location**

#### Test 1.1: Unsupported City
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Tìm hotel ở Đà Lạt",
    "locale": "vi",
    "debug": true
  }'
```

**Expected Response:**
```json
{
    "location_status": "unsupported",
    "canonical_area": null,
    "anchor_lat": null,
    "anchor_lon": null,
    "follow_up_question": "Hiện mình chỉ hỗ trợ TP HCM, Hà Nội...",
    "ready_for_recommendation": false,
    "can_show_recommendations": false
}
```

**What's wrong:**
- ❌ No coordinates to search from
- ❌ Recommendation engine can't proceed
- ❌ User confused

---

#### Test 1.2: Vague Location
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hotel ở phía nam"
  }'
```

**Expected:** `location_status: "unresolved"`
**Why:** "phía nam" (south) is too vague, not in gazetteer

---

#### Test 1.3: International City
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hotel ở Bangkok"
  }'
```

**Expected:** `location_status: "unsupported"`

---

### **ERROR 2: Budget Parsing Fails**

#### Test 2.1: Qualitative Budget (No Numbers)
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hotel ở Q1, budget rẻ nhất có thể",
    "locale": "vi"
  }'
```

**Expected:**
```json
{
    "slots": {
        "budget": null,
        "budget_min": null,
        "budget_max": null,
        "priorities": ["cheap"]  // ← Only this captured
    },
    "missing_slots": ["budget"],
    "follow_up_question": "Bạn có ngân sách bao nhiêu?"
}
```

**Why:** "rẻ nhất" ≠ numeric value

---

#### Test 2.2: Approximate Budget (Vague Range)
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Tầm 100k thôi"
  }'
```

**Likely issue:** "Tầm" (approximately) might not extract as 100k
- May return: `budget: null` or `budget: 100000` depending on regex

---

#### Test 2.3: Wrong Budget Unit
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hotel 200 per night",
    "locale": "en"
  }'
```

**Issue:** 
- Parser extracts 200 as numeric
- But 200 (USD) ≠ 200 (VND)
- System treats as 200 VND
- Result: Zero matches (rooms cost 50k+ VND)

---

#### Test 2.4: Inverted Budget Range (Bug Test)
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hotel từ 500k đến 100k"
  }'
```

**Expected:** Should auto-swap
```json
{
    "slots": {
        "budget_min": 100000,
        "budget_max": 500000
    }
}
```

**Code:** In `slot_validator.py:138-139`
```python
if budget_min > budget_max:
    budget_min, budget_max = budget_max, budget_min
```

✅ Works correctly (auto-fixed)

---

### **ERROR 3: Location Conflict Loop**

#### Test 3.1: Multiple Areas (Conflict)
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hotel ở Quận 1 hay Quận 3"
  }'
```

**Expected Response:**
```json
{
    "location_status": "conflict",
    "location_candidates": [
        {"canonical_area": "Quận 1 (TP HCM)"},
        {"canonical_area": "Quận 3 (TP HCM)"}
    ],
    "follow_up_question": "Bạn xác nhận giúp mình muốn tìm ở đâu? (Quận 1 hay Quận 3)",
    "ready_for_recommendation": false
}
```

---

#### Test 3.2: User Doesn't Commit Choice (Loop Test)
```bash
# First request
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{"text": "Hotel ở Q1 hay Q3"}'
# → conflict detected

# User replies evasively
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "Hoặc được cái nào",
    "context_slots": {previous_slots}
  }'
```

**Issue:**
- Still ambiguous
- System asks again: "Chọn Q1 hay Q3?"
- User keeps saying "không quan trọng"
- Loop! 🔄

---

### **ERROR 4: Missing Amenity Support**

#### Test 4.1: Unsupported Amenity
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Homestay ở Q1 có nước nóng"
  }'
```

**Expected:**
```json
{
    "slots": {
        "required_amenities": [],  // ← Hot water not recognized!
        "area": "Quận 1 (TP HCM)"
    }
}
```

**Why:** "nước nóng" not in AMENITY_ALIASES

**Supported amenities only:**
```
wifi, pool, parking, kitchen, air_conditioner, washing_machine
```

---

#### Test 4.2: Similar But Different Amenity
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Hotel có tủ lạnh và lò vi sóng"  (fridge & microwave)
  }'
```

**Result:** Both ignored (not in list)

---

### **ERROR 5: Guest Count Validation**

#### Test 5.1: Excessive Guest Count
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Hotel cho 200 người"
  }'
```

**Expected:**
```json
{
    "slots": {
        "guest_count": null  // ← Capped/rejected at 30
    }
}
```

**Code:** `slot_validator.py:145`
```python
slots["guest_count"] = guest_count if guest_count and 1 <= guest_count <= 30 else None
```

---

#### Test 5.2: Decimal Guest Count
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Cho 2.5 người"
  }'
```

**Result:** Probably `guest_count: null` (not matching integer regex)

---

### **ERROR 6: Trip Days Validation**

#### Test 6.1: Too Long Stay
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Tìm chỗ ở 600 ngày"
  }'
```

**Expected:**
```json
{
    "slots": {
        "trip_days": null  // ← Capped at 365
    }
}
```

**Code:** `slot_validator.py:148`
```python
slots["trip_days"] = trip_days if trip_days and 1 <= trip_days <= 365 else None
```

---

### **ERROR 7: Type Ambiguity**

#### Test 7.1: Multiple Accommodation Types
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Tôi muốn khách sạn hay homestay"
  }'
```

**Expected:**
```json
{
    "slots": {
        "accommodation_types": ["hotel", "homestay"],
        "preferred_type": null,
        "type_choice_multiple": true
    }
}
```

**Impact:** Recommendation engine searches both types (broader results)

---

#### Test 7.2: Unrecognized Type
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Tìm dorm ở Q1"
  }'
```

**Expected:**
```json
{
    "slots": {
        "accommodation_type": "hostel"  // ← "dorm" alias mapped
    }
}
```

But if type not in aliases → `accommodation_type: null`

---

### **ERROR 8: Terminal Intent Too Early (v2 Pipeline)**

#### Test 8.1: Mixed Greeting + Search
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Chào, tôi muốn tìm hotel ở Q1"
  }'
```

**Risk:** 
- If v2 pipeline enabled
- And router detects "greeting" intent first
- May return greeting response instead of parsing search
- ⚠️ Search intent lost!

---

### **ERROR 9: No Area + No Budget = Broken Recommendation**

#### Test 9.1: Only Guest Count
```bash
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "Cho 3 người"
  }'
```

**Expected:**
```json
{
    "ready_for_recommendation": false,
    "can_show_recommendations": false,
    "missing_slots": ["area", "budget"],
    "follow_up_question": "Bạn muốn tìm ở đâu?"
}
```

**If incorrectly marked ready:**
```json
{
    "ready_for_recommendation": true,
    "created_preference": true,
    "pref_id": "xyz"
}
// But NO AREA specified!
// Downstream: Search all hotels everywhere
// ❌ Wrong!
```

---

### **ERROR 10: Bad Geolocation Coordinates**

#### Test 10.1: Out of Bounds Latitude
```bash
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "Tìm hotel gần tôi",
    "user_location": {
        "lat": 91,    // ❌ Invalid (> 90)
        "lon": 106.5,
        "accuracy": 100
    }
  }'
```

**Expected:** Coordinates ignored silently
```python
# views.py:245
if not (-90 <= lat <= 90 and -180 <= lon <= 180):
    return None
```

---

#### Test 10.2: Missing Accuracy Field
```bash
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "Tìm gần tôi",
    "user_location": {
        "lat": 10.77,
        "lon": 106.70
        // Missing "accuracy"
    }
  }'
```

**Result:** Coordinates accepted, but `accuracy` field skipped

---

### **ERROR 11: Context Slot Merging Issues**

#### Test 11.1: Array Slot Merge
```bash
# First request
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Hotel có wifi"
  }'
# Returns: required_amenities: ["wifi"]

# Second request (with context)
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "với pool",
    "context_slots": {
        "required_amenities": ["wifi"]
    }
  }'
```

**Expected:** Merge both → `["wifi", "pool"]`

**Code:** `views.py:226-227`
```python
base = merged.get(key) or []
merged[key] = list(dict.fromkeys([*base, *add]))
```

✅ Works (deduplicates)

---

### **ERROR 12: Nominatim Geocoder Timeout**

#### Test 12.1: Specific Street Address
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Hotel ở đường Nguyễn Huệ, Q1"
  }'
```

**Flow:**
```
extract_location_mentions("duong nguyen hue q1")
→ Finds "q1"
→ Status: "ok" (area resolved)

But what if area NOT resolved?
→ _try_geocode_fallback()
→ Call Nominatim API
→ If timeout: return None
→ Fallback to "unresolved"
```

**To test timeout:**
- Run chatbot on slow connection
- Or Nominatim server down

---

### **ERROR 13: LLM Model Not Available**

#### Test 13.1: Force LLM but Model Down
```bash
# Set in .env
CHAT_API_LLM_STRATEGY="always"

curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Tìm apartment ở Q1, 200k"
  }'
```

**If model unavailable:**
```json
{
    "error": "Parser temporarily unavailable",
    "status": 503
}
```

**Code:** `parser_service.py:1843-1846`
```python
except Exception:
    logger.exception("chat_api hf parser failed before fallback")
    fallback_result["llm_called"] = True
    return fallback_result
```

---

### **ERROR 14: Groq Only Works When No Area**

#### Test 14.1: Area Already Found
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Homestay ở quanh Bến Thành"
  }'
```

**Flow:**
```
Rule-based:
  area: "Quận 1" (Bến Thành landmark in Q1)
  ✓ has_area = true

Groq check (groq_llm.py:1871-1878):
  if has_area:
      return result  # DON'T CALL GROQ

Problem: If rule-based missed "homestay" type
→ Groq could have fixed it
→ But not called because area already found
→ Lost the type info!
```

---

### **ERROR 15: Circular Context Slots (Rare)**

#### Test 15.1: Craft Malicious Context
```bash
# This is a theoretical attack - don't try on production!
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "test",
    "context_slots": {
        "area": "Q1",
        "prev": {"nested": {"ref": null}}  // Could cause recursion
    }
  }'
```

**Unlikely to happen** with normal usage, but poor validation

---

## 🎯 CRITICAL TEST SCENARIOS

### Scenario A: User Gets Zero Results
```bash
# Combination that breaks recommendation
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "Khách sạn",
    "confirmed_slots": {
        "preferred_type": "hotel",
        "guest_count": 200,  # Too high
        "budget": 5         # Too low
    }
  }'
# Result: No hotels match these extreme filters
```

---

### Scenario B: Loop in Clarification
```bash
# First: ambiguous
Request 1: "Hotel ở Q1 hay Q3"
→ Conflict → Ask which

# User evasive
Request 2: "Không quan trọng"
→ Still conflict
→ Ask which again

# Loop!
Request 3: "Hoặc được"
→ Still conflict
→ Ask which AGAIN
```

---

### Scenario C: Mixed Language
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Hotel ở Q1, 3 people, có wifi",
    "locale": "vi"
  }'
```

**Issue:** Response in Vietnamese but input mixed English
- "people" might not parse correctly
- "wifi" recognized (common word)

---

### Scenario D: Large Input Text
```bash
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{
    "text": "Tôi muốn tìm khách sạn ở Quận 1 TP HCM có wifi và hồ bơi và điều hòa và máy giặt và bếp và đỗ xe và phòng sạch sẽ và view đẹp và gần trung tâm và yên tĩnh và... (10000 words)"
  }'
```

**Possible issues:**
- Regex performance
- Parser timeout
- Lost low-priority amenities

---

## ✅ PASSING TEST CASES (Expected to Work)

```bash
# Simple search
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{"text": "Hotel ở Q1, 100k, 3 người, 2 đêm"}'
→ Extracted: area, budget, guest_count, trip_days ✓

# Landmark
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{"text": "Homestay gần Bến Thành"}'
→ Resolved: Q1 area, landmark-based search ✓

# Budget range
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{"text": "Apartment từ 500k đến 1tr ở Q3"}'
→ Extracted: budget_min, budget_max ✓

# Geolocation
curl -X POST http://localhost:8000/api/chat/submit_message \
  -d '{
    "text": "Tìm gần tôi",
    "user_location": {"lat": 10.77, "lon": 106.70, "accuracy": 50}
  }'
→ Sets location_mode: "near_user" ✓

# Amenities
curl -X POST http://localhost:8000/api/chat/parse_message \
  -d '{"text": "Hotel có wifi, pool, parking"}'
→ Extracted: ["wifi", "pool", "parking"] ✓
```

---

## 📊 Coverage Matrix

| Test Case | Error | Bucket | Severity |
|---|---|---|---|
| T1.1 | Unsupported city | #3 | 🔴 |
| T2.1 | Qualitative budget | #2 | 🔴 |
| T3.1 | Location conflict | #3 | 🟠 |
| T4.1 | Amenity not supported | #2 | 🟡 |
| T5.1 | Guest count overflow | #2 | 🟡 |
| T6.1 | Trip days overflow | #2 | 🟡 |
| T7.1 | Type ambiguity | #2 | 🟢 |
| T8.1 | Terminal intent early | #1 | 🟠 |
| T9.1 | No area for recommendation | #4 | 🔴 |
| T10.1 | Bad geolocation | #5 | 🟠 |
| T11.1 | Merge error | #5 | 🟡 |
| T12.1 | Geocoder timeout | #3 | 🟡 |
| T13.1 | LLM unavailable | #5 | 🟠 |
| T14.1 | Groq not called | #5 | 🟢 |
| T15.1 | Recursion | #5 | 🔴 |

