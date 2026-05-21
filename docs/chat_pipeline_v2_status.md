# Chat Pipeline V2 — Status

Last updated: 2026-05-20

## Feature flag

```python
# accommodation_project/settings.py
CHAT_PIPELINE_V2_ENABLED = os.getenv("CHAT_PIPELINE_V2_ENABLED", "0") == "1"
```

**Default: OFF.** Production stays on v1.

## Current status

| Mode | Test failures | Notes |
|------|---------------|-------|
| V1 (flag off) | 10 | Pre-existing baseline. No regression introduced. |
| V2 (flag on)  | 49 | Down from 79 at start (Tasks 1+2+3+4+5+7 + context carry-over applied). |

## Behaviour fixed in this push (Tasks 1 + 2 + 3 + 4 + 5 + 7 + context carry-over)

### Area canonicalization
Areas now return canonical display form everywhere (`slots.area`, `canonical_area`, `search_intent_v2.area`).
- `"quan 3"`, `"q3"`, `"Q3"`, `"quận 3"` → `"Quận 3"`
- `"thuduc"`, `"thu duc"` → `"Thủ Đức"`
- `"binhthanh"`, `"binh thanh"` → `"Bình Thạnh"`
- `"govap"`, `"go vap"` → `"Gò Vấp"`
- `"tp hcm"`, `"sai gon"`, `"ho chi minh"` → `"TP HCM"`
- `"ha noi"`, `"hanoi"` → `"Hà Nội"`

### Compact aliases
`_detect_area()` now consults the gazetteer alias index (≥4 chars) AND admin-suffix patterns, so single-token compact forms classify as `area`.

### "gần <area>" semantic
"gần thuduc", "gần Quận 3" no longer route to `landmark_or_poi`/Nominatim. The classifier detects when the near-cue remainder is a known area and routes to `DirectAreaStrategy`.

### Multi-choice & conflict (Task 3)
- "Hà Nội hoặc TP HCM cho 2 người" → `location_status="multiple_choice"`, `canonical_area=None`, `ready=False`
- "Tôi muốn ở gần Bến Thành ở Hà Nội" → `location_status="conflict"`, `canonical_area=None`, `ready=False`
- "Landmark 81 ở Đồng Nai" → `conflict`
- Single-area queries unaffected.

Implementation: new `MultiChoiceConflictStrategy` (order 35) wraps v1's `chat_api.location_resolver.resolve_location()` so the multi-mention / choice-phrase detection logic is reused, not duplicated.

### City-center mode (Task 4)
- "trung tâm thành phố", "gần trung tâm", "downtown" → `location_mode="city_center"`, `anchor_kind="city_center"`, `geocoder_called=False`
- "trung tâm Hà Nội" / "khách sạn gần trung tâm TP HCM" → canonical city detected
- "truang tâm thành phố" (typo) → still detected (typo correction applied)
- "gần bưu điện trung tâm thành phố" → stays `near_anchor` (POI, not city center)

Implementation: new `CityCenterStrategy` (order 32) delegates to v1's `chat_api.city_center.resolve_city_center`. Classifier detects city-center phrase via v1's `detect_city_center_intent` (with `normalize_common_typos` pre-applied).

### Hotel/Resort extraction (Task 5)
- "Tìm resort ở Phú Quốc" → `slots["unsupported_preferred_type"] = "resort"`, `preferred_type=None`
- "Hotel or apartment in Hanoi" → `preferred_type=None`, `accommodation_types=["hotel","apartment"]`, `type_choice_multiple=True`

Implementation: `_finalize_v2_result` calls v1's `find_unsupported_type_candidates` and `has_type_choice_connector` to mirror v1 type-handling.

### Off-topic / greeting gating (Task 7)
- "chào cậu", "hello" → `conversation_intent="greeting"`, `ready_for_recommendation=False`
- "cảm ơn" → `intent="thanks"`
- "hôm nay trời mưa không" → `intent="off_topic"`, `can_show_recommendations=False`
- Submit endpoint: terminal intents don't create UserPreference

Implementation: `parse_user_text` runs the v1 domain router BEFORE v2 NLU. If the router classifies the message as a terminal intent (greeting / off_topic / thanks / help / goodbye), it short-circuits to `_terminal_response` — same path v1 uses.

### Multi-turn context carry-over
- "Khách sạn ở Hà Nội cho 2 người" → "900k 2 ngày" → area carried from context, `location_status="ok"`

Implementation: `_finalize_v2_result` promotes context's area to current location when the current message produced no own location signal.

## Files changed (this push)

| File | Change |
|------|--------|
| `chat_api/location_gazetteer.py` | + `canonicalize_area_name()`, `_alias_to_canonical_index()`, `_V2_EXTRA_CITY_SYNONYMS` (v2-only, doesn't leak to v1) |
| `chat_api/nlu/input_classifier_v2.py` | `_detect_area` uses gazetteer aliases; `q\.?\d` admin pattern; `gần <area>` shortcut; city_center detection step |
| `chat_api/nlu/search_intent_builder.py` | `area` and `resolved.canonical_area` use canonicalized form |
| `chat_api/location/strategies/direct_area.py` | `canonical_area`/`display_label` use canonicalized form |
| `chat_api/location/strategies/multi_choice_conflict.py` | **NEW** strategy wrapping v1 multi-choice/conflict logic |
| `chat_api/location/strategies/city_center.py` | **NEW** strategy delegating to v1 `city_center` module |
| `chat_api/location/resolver.py` | Register new MultiChoiceConflict + CityCenter strategies |
| `chat_api/nlu/dto.py` | `SearchIntent.to_dict()` for JSON-safe serialization |
| `chat_api/application/chat_pipeline.py` | Always emit dict for `search_intent_v2` |
| `chat_api/parser_service.py` | Keep `search_intent_v2` in response so bridge can take v2 path |

## Remaining failures groups (49 in V2 mode)

| Group | Approx count | Status |
|-------|-------------:|--------|
| G3 — Multi-choice/conflict/ambiguous | 8 | TODO |
| G4 — City-center mode | 3 | TODO |
| G5 — Hotel/Resort/Accommodation name | 6 | TODO |
| G6 — POI category / map suggestions | 22 | TODO |
| G7 — Off-topic / greeting / submit gating | 9 | TODO |
| G8 — Multi-turn / follow-up / confirmation | 9 | TODO |
| G9 — Pre-existing v1 failures (not v2-caused) | 10 | Out of scope |
| Unclassified / dependent | ~7 | Depend on above |

See `docs/chat_pipeline_v2_gap_report.md` for the full test list per group.

## Test commands

```bash
# v2 enabled
CHAT_PIPELINE_V2_ENABLED=1 python manage.py test chat_api.tests \
  --settings=accommodation_project.test_settings

# v1 (regression baseline)
CHAT_PIPELINE_V2_ENABLED=0 python manage.py test chat_api.tests \
  --settings=accommodation_project.test_settings
```

## Safety checklist

- [x] `models.py` untouched
- [x] No new migrations
- [x] `db.sqlite3` untouched
- [x] No DB schema changes
- [x] v1 pipeline still present and default
- [x] `CHAT_PIPELINE_V2_ENABLED` default = `0` in `settings.py`
- [x] v1 test failure count unchanged (10 → 10)
- [x] All new aliases/synonyms use gazetteer config, no rule-engine hard-coding

## Why v2 is not production-ready yet

74 V2-mode failures cluster into 6 functional groups (G3–G8) that need
dedicated NLU work — multi-choice detection, city-center strategy,
hotel-name extraction, POI/map-suggestion routing, off-topic guards,
multi-turn follow-up handling. Each group is independent and can be
delivered as a separate change. See gap report for prioritization.

Run with V1 in production until G3–G7 are addressed.
