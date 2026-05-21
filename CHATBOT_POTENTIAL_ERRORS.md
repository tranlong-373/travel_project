# Danh Sách Các Lỗi/Vấn Đề Tiềm Ẩn Của Chatbot

## 🔴 CRITICAL ERRORS (Lỗi Nghiêm Trọng)

### 1. **Location Resolution Fails → Unresolved Area**
**Vấn đề:** Khi user nói tên khu vực không nằm trong database
```
Input: "Tìm hotel ở Đà Lạt"
↓
Location resolver không tìm thấy "Da Lat" trong:
  • supported_areas.json
  • landmarks.json
  • location_rules.json
↓
Status: "unsupported" hoặc "unresolved"
```

**Kết quả:**
- ❌ `canonical_area = None`
- ❌ `anchor_lat, anchor_lon = None`
- ❌ `filter_tree.location = empty`
- ❌ Không thể tạo preference → Recommendation fails
- 😞 User phải hỏi lại "Bạn muốn ở đâu?"

**Edge cases:**
- Tên địa điểm có dấu nhưng user gõ không dấu: "Da Lat" vs "Đà Lạt" → May là normalize_key() giải quyết
- Abbreviations không được support: "Tây Ninh" nhưng user nói "TN"
- Typos: "Quan 1" vs "Quan I" (số 1 vs chữ I)

---

### 2. **Budget Parsing Fails**
**Vấn đề:** User nói budget nhưng parser không trích xuất được số
```
Input: "Hotel khoảng mười triệu"
↓
extract_budget_bounds() → Không match pattern
↓
budget = None
```

**Pattern mà parser hiểu:**
```
✓ 100k, 100000
✓ 1.2tr, 1.2 triệu  
✓ 500 đô, 500$
✓ từ 50k đến 100k

✗ "khoảng triệu"        (too vague)
✗ "một triệu đồng"       (written out in words - depends on support)
✗ "rẻ nhất có thể"       (qualitative, not numeric)
✗ "tầm 100k"            (tầm = approximate, unclear)
```

**Kết quả:** 
- `budget = None` 
- Missing core slot → Ask follow-up
- Recommendation may fail if budget critical

---

### 3. **Location Conflict Detection → Stuck in Loop**
**Vấn đề:** User mentions multiple areas, system asks "Chọn cái nào?"
```
Input: "Hotel ở Q1 hay Q2"
↓
extract_location_mentions() → Found: Q1, Q2
↓
Status: "conflict"
↓
Response: "Bạn muốn ở Q1 hay Q2?"
↓
User replies: "Hoặc cái nào"
↓
Still conflict → Stuck asking same question again
```

**Issue:** Loop trong clarification logic
- `_has_choice_phrase()` detect "hoặc" (or)
- Nhưng user không commit choice → Conflict persists
- Chatbot keep asking same question

---

### 4. **Accommodion Type Ambiguity**
**Vấn đề:** User mentions multiple accommodation types nhưng không rõ ý
```
Input: "Hotel hay homestay ở Q1?"
↓
accommodation_types = ["hotel", "homestay"]
type_choice_multiple = True
↓
Unclear which type user prefers
```

**Kết quả:**
- `preferred_type = None` (not auto-picking)
- May cause issues downstream
- Recommendation engine receives both types → Broader results

---

## 🟠 HIGH PRIORITY ERRORS

### 5. **User Location (Browser Geolocation) Issues**

**a) Invalid coordinates**
```python
user_location = {
    "lat": 91,    # ❌ Out of bounds (-90 to 90)
    "lon": 106.5
}
↓
_read_user_location() → Returns None
↓
location ignored, search uses area instead
```

**Code validation:**
```python
if not (-90 <= lat <= 90 and -180 <= lon <= 180):
    return None  # Silently drops bad coords
```

**b) Missing accuracy field**
```python
user_location = {
    "lat": 10.77,
    "lon": 106.70,
    # Missing "accuracy"
}
↓
No error thrown, just skipped
↓
Result missing accuracy info
```

**c) Geolocation denied by user**
```
Browser: User clicks "Deny" on geolocation
↓
Frontend doesn't send user_location
↓
System falls back to area search
↓
If no area mentioned → Unresolved location
```

---

### 6. **Budget Min/Max Validation Issues**

**a) Inverted budget range**
```python
Input: "từ 500k đến 100k"  # User typo: min > max
↓
budget_min = 500000
budget_max = 100000
↓
Code fix: if budget_min > budget_max: swap them
✓ Fixed automatically
```

But issues if logic elsewhere assumes max >= min:
```python
# In recommendation filtering:
WHERE price >= budget_min AND price <= budget_max
# If swapped: WHERE price >= 100k AND price <= 500k ✓ Works
```

**b) Unrealistic budget values**
```
Input: "Khách sạn 5 đô"
↓
budget_max = 5  # USD, but stored as VND?
↓
No validation → Passes through
↓
Recommendation query: WHERE price <= 5 VND
↓
Result: 🔒 ZERO matches (minimum rooms cost 50k+)
```

**c) Budget precision loss**
```python
budget_max = 1_234_567.8  # Float with decimals
↓
Stored as int → 1234567 (truncated)
↓
Small rounding error, usually not critical
```

---

### 7. **Guest Count Edge Cases**

**a) Boundary violations**
```python
Input: "200 người"
↓
extract_guest_count() → 200
↓
validate_slots(): if guest_count > 30: guest_count = None
↓
Result: guest_count = None (capped at 30)
```
User thinks searching for 200 but system searches without this filter

**b) Zero or negative**
```
Input: "0 người"  or "-5 người"
↓
extract_guest_count() → 0 or -5
↓
validate_slots(): if not (1 <= count <= 30): count = None
✓ Filtered out
```

**c) Decimal guest counts**
```
Input: "2.5 người"
↓
extract_guest_count() → None (not matching integer pattern)
↓
Ignored, no error
```

---

### 8. **Trip Days Validation**
```python
Input: "600 ngày" (18+ months)
↓
extract_trip_days() → 600
↓
validate_slots(): if not (1 <= days <= 365): days = None
✓ Filtered to None
↓
But user expected 600 days search → Gets None instead
```

---

## 🟡 MEDIUM PRIORITY ERRORS

### 9. **Amenities/Features Not in Enum**
```python
Input: "Hotel có nước nóng"  (hot water)
↓
"nuoc nong" not in AMENITY_ALIASES
↓
extract_required_amenities() → [] (empty, ignored)
↓
Amenity requirement lost
```

**Supported amenities only:**
```
wifi, pool, parking, kitchen, 
air_conditioner, washing_machine
```

**Missing common requests:**
- Nước nóng (hot water)
- Tủ lạnh (refrigerator)
- Tivi (TV)
- Cơm chiều (afternoon snack)
- Vệ sinh tốt (clean)
- Nhân viên thân thiện (friendly staff)

→ Filtered out silently, no error message

---

### 10. **Priorities/Special Requirements Overflow**
```python
Input: "High rating, cheap, near center, near beach, quiet, clean, safe"
↓
extract_priorities() → ["high_rating", "cheap", "near_center", "near_beach", ...]
↓
All extracted fine, but recommendation engine may:
  • Rank by first priority only
  • Ignore lower priorities
  • Performance degrade with too many filters
```

---

### 11. **Text Normalization Loses Information**
```python
Input: "Phòng DELUXE gần sân bay" (DELUXE room near airport)
↓
normalize_user_text():
  • lowercase → "phong deluxe gan san bay"
  • Remove special chars
  • Remove accents → "phong deluxe gan san bay"
↓
"deluxe" room type lost (not in ALLOWED_TYPES)
↓
Result: location="san bay" only, room type ignored
```

---

### 12. **Nominatim Geocoder Timeout**
```python
_try_geocode_fallback() → Call Nominatim API
↓
Nominatim server slow/down
↓
API call hangs >5 seconds
↓
System timeout → Returns None
↓
fallback to gazetteer (or unresolved)
```

**Code:**
```python
try:
    coords = geocode_street_address(text)  # May timeout
    if coords is None:
        return None
except Exception:
    return None
```

---

### 13. **LLM Model Failures**
**When CHAT_API_LLM_STRATEGY="auto":**
```
Rule-based parser incomplete? 
  → Try HF transformer model
    ↓
  Model unavailable/crashed?
    → Fall back to rule-based (again)
    ↓
  If rule-based already ran and incomplete?
    → Return incomplete result to user
```

**Chain:**
```
parse_user_text()
├─ Rule-based → Incomplete (missing area)
├─ Try HF LLM → Timeout/error
├─ Catch exception
└─ Return rule-based result (still incomplete)
   └─ User gets confused
```

---

### 14. **Groq LLM Only Works When Area NOT Found**
```python
# groq_llm.py, line 1868-1878:
has_area = bool(
    result.get("canonical_area")
    or slots.get("area")
    or result.get("anchor_lat") is not None
)

if has_area:
    return result  # Don't call Groq

# Problem: If user says:
# "Homestay gần như Bến Thành có wifi"
# But Bến Thành resolve to Q1 area
# → has_area=True → Groq NOT called
# → Lost the "homestay" type info if rule-based didn't catch it
```

---

### 15. **Missing Slots Not Always Asked**
```python
CORE_SLOTS = ["area", "budget", "guest_count", "trip_days"]

ready_for_recommendation = (
    any core slot has value
)

Problem: User could say:
"Khách sạn 3 người" (hotel, 3 people)
↓
Extracted: type="hotel", guest_count=3
✓ But no area!
↓
missing_slots = ["area"]
↓
Should ask "Bạn muốn tìm ở đâu?"
✓ Working correctly

But edge case:
If area=None but budget=100k, guest_count=3
→ ready_for_recommendation=True
→ Creates preference WITHOUT area
→ Downstream query: WHERE budget<=100k AND guests>=3
→ Returns hotels from ALL areas (worldwide??)
→ Wrong!
```

---

## 🟢 LOW PRIORITY / EDGE CASES

### 16. **Overlapping Amenities in Text**
```
Input: "Điều hòa và máy lạnh" (AC and cooling - redundant)
↓
Both patterns match:
  "dieu hoa" → air_conditioner
  "may lanh" → air_conditioner
↓
required_amenities = ["air_conditioner", "air_conditioner"]
↓
Filter tree deduplicates → ["air_conditioner"]
✓ Works fine
```

---

### 17. **District Detection (HCM Specific)**
```python
# Parser detects "Quận X" pattern
HCM_DISTRICT_PATTERN = r"\b(?:quận|quan|q\.?|district)\s*(\d{1,2})\b"

Input: "Quận 13"  # Invalid (max is 12)
↓
_extract_area_fallback() → _format_hcm_district(13)
↓
if HCM_DISTRICT_MIN (1) <= district (13) <= HCM_DISTRICT_MAX (12):
    return formatted
→ Returns None (out of range)
✓ Correctly rejected

But issue: User meant "Quận 1, số 3 tòa nhà"
↓
Parser extracts "quận 1" correctly
✓ Working
```

---

### 18. **Landmark Importance Conflicts**
```
# landmarks.json has landmarks with importance scores
"Bến Thành": importance=95
"Bên Thành" (typo): importance=50

User: "gần Bên Thành"
↓
Normalize: "ben thanh"
↓
Both match? Only highest importance returned
✓ Works correctly
```

---

### 19. **Context Slot Merging Bugs**

**Bug 1: Array slot merging**
```python
def _merge_payload(context_slots, payload):
    for key in {"required_amenities", "priorities"}:
        base = merged.get(key) or []
        add = value if isinstance(value, list) else [value]
        merged[key] = list(dict.fromkeys([*base, *add]))

# Problem: dict.fromkeys() removes order
# If order matters → Could be issue
```

**Bug 2: Budget override**
```python
if "budget_max" in payload and "budget" not in payload:
    merged["budget"] = payload["budget_max"]

# What if both exist?
# budget_max takes precedence
# But budget could be different value?
```

---

### 20. **Terminal Intent Detection Too Early**

**In v2 pipeline:**
```python
if router_early["intent"] in TERMINAL_INTENTS:
    return _terminal_response(...)

TERMINAL_INTENTS = {"off_topic", "greeting", "thanks", "help", "goodbye"}

Problem: User says:
"Xin chào, tôi muốn tìm hotel ở Q1"
(Hello, I want to find hotel in Q1)
↓
Might detect "greeting" intent
↓
Return greeting response instead of search
✗ Lost the search request
```

---

### 21. **Protected Spans Not Always Respected**
```python
protected_spans = [(0, 10)]  # Don't touch characters 0-10

But slot extraction runs on:
    normalize_user_text() → loses span info
    ↓
Protected info might get normalized/changed
↓
Conflicts with original spans

Edge case: Brand names like "Melia Hotel"
→ Might be protected but normalize_key() lowercases it
→ Original capitalization lost
```

---

### 22. **Locale Handling**
```python
Input: locale="zh"  (Chinese)
↓
_normalize_locale():
    if locale not in ["vi", "en"]:
        locale = "vi"
↓
Silently falls back to Vietnamese
✓ Reasonable but user might not know

Response in Vietnamese when they expect Chinese
```

---

### 23. **Ambiguous Type Extraction**
```
Input: "Muốn tìm một chỗ để ở có tường gạch"
(Looking for accommodation with brick walls)
↓
"chỗ để ở" = GENERIC_LODGING_PHRASE
"tường gạch" ≠ type
↓
accommodation_types = [] (empty, generic)
✓ Correct - just generic
```

---

### 24. **Budget Unit Confusion**
```
Input: "300 per night"  (assuming USD)
↓
extract_budget_bounds("300 per night")
↓
Parser might extract 300 in Vietnamese context
↓
But: 300 VND ≠ 300 USD
↓
If system assumes VND → budget way too low
→ Zero results
```

---

### 25. **Caching Issues (If Enabled)**
```python
# location resolver caches _reference_data()
@lru_cache(maxsize=1)
def _reference_data():
    return {...}

# If data files update:
# supported_areas.json changes
# But cache still holds old data
# → New areas not recognized until restart
```

---

## 🔵 WORKFLOW EDGE CASES

### 26. **No Area + No Budget → Recommendation Impossible**
```
Input: "Khách sạn cho 3 người"
↓
Extracted: type="hotel", guest_count=3
✓ Missing: area, budget
↓
missing_slots = ["area", "budget"]
↓
Can create preference? 
   ready_for_recommendation = (has_area OR other critical)
   → False
✓ Correctly asks for more info
```

---

### 27. **Selected Place (Map Marker) Not Processing Correctly**
```python
# In views.py:
selected_place = raw_slots.get("selected_place")
↓
if selected_place and selected_place.get("lat") is not None:
    slots["area"] = None  # Override area!
    slots["location_mode"] = "near_anchor"
    slots["location_phrase"] = selected_place.get("name")

Problem: User confirms place marker on map
→ All previous area search info lost
→ Might not be desired behavior
```

---

### 28. **V2 Pipeline Optional But Fallback Weak**
```python
CHAT_PIPELINE_V2_ENABLED = False  # Default

if CHAT_PIPELINE_V2_ENABLED:
    # New NLU pipeline
else:
    # Rule-based legacy
    
If v2 fails:
    except Exception:
        logger.exception("v2 failed, falling back to v1")
    # Falls back to rule-based
    
But rule-based might be incomplete
→ Returns incomplete result
```

---

### 29. **LLM Strategy "auto" Heuristic**
```python
strategy = _llm_strategy()  # Returns "auto", "never", "always"

if strategy == "auto" and _can_answer_fast(fast_result):
    return fast_result  # Don't use LLM

_can_answer_fast() criteria:
    • Has location? 
    • Has enough slots?
    • (criteria not fully documented)

If heuristic wrong → Misses LLM improvement
```

---

### 30. **Confirmation Required Ambiguity**
```python
result = {
    "confirmation_required": False,
    "awaiting_confirmation": False,
    "ready_for_recommendation": False,
    ...
}

When should confirmation_required = True?
• Code never sets it to True?
• Dead field? Bug?

If user needs confirmation but field=False
→ Confusing state
```

---

## 🚨 POTENTIAL RUNTIME CRASHES

### 31. **JSON Serialization Errors**
```python
# If slots contain non-serializable objects:
result["slots"] = {
    "area": obj_with_custom_class()  # Not JSON serializable
}
↓
JsonResponse(result) → TypeError
↓
500 error
```

---

### 32. **Circular Reference in Context Slots**
```python
context_slots = {
    "area": "Q1",
    "self": context_slots  # Circular
}
↓
merge_slot_context() → Infinite loop?
↓
RecursionError
```

---

### 33. **Out of Memory on Large Aliases**
```python
# If supported_areas.json + landmarks.json huge:
@lru_cache(maxsize=1)
def _reference_data():
    supported_areas = _load_json("supported_areas.json")  # 100k entries
    landmarks = _load_json("landmarks.json")  # 500k entries
    aliases = []  # Iterates all
    
If aliases array grows too large:
    → Memory exhaustion on server
    → Service crash
```

---

### 34. **Regex DoS (Denial of Service)**
```python
# If malicious input:
text = "a" * 10000 + "q1"
↓
extract_location_mentions() → re.finditer()
↓
Regex might take exponential time on bad patterns
↓
Server CPU spike
↓
DoS vulnerability
```

---

## 📋 SUMMARY TABLE

| Error Category | Severity | Likelihood | Impact |
|---|---|---|---|
| Unresolved location | 🔴 Critical | High | Zero recommendations |
| Budget parse fail | 🔴 Critical | Medium | Wrong price range |
| Location conflict loop | 🟠 High | Medium | User stuck |
| Bad geolocation coords | 🟠 High | Low | Search falls back |
| Amenity not supported | 🟡 Medium | High | Lost requirement |
| LLM fallback incomplete | 🟡 Medium | Medium | Partial results |
| Context merge bug | 🟡 Medium | Low | Wrong slot values |
| Type ambiguity | 🟢 Low | High | Broader results (OK) |
| Locale fallback | 🟢 Low | Low | Wrong language |
| Memory exhaustion | 🔴 Critical | Very low | Server crash |

---

## 🛠️ RECOMMENDATIONS

### **Fix Critical Issues:**
1. ✅ **Require area input** before creating preference
2. ✅ **Validate budget numeric range** (not just null check)
3. ✅ **Detect location conflict loop** → Auto-escalate to operator
4. ✅ **Support more amenities** (hot water, fridge, TV, etc.)
5. ✅ **Cache invalidation** when data files change

### **Improve Robustness:**
6. Add explicit error messages for unsupported locations
7. Better amenity/priority expansion (use NLP to map unknown → known)
8. Implement maximum retry count for clarifications
9. Add request timeouts for Nominatim geocoder
10. Log all "None" slot values for analysis

### **Add Validation:**
11. Require minimum 1 core slot before recommendation
12. Validate budget range makes sense (min <= max)
13. Check guest_count + room_count compatibility
14. Verify trip_days + check_in/check_out consistency

