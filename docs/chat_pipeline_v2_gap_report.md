# Chat Pipeline V2 — Gap Report

Generated: 2026-05-20
Command run: `CHAT_PIPELINE_V2_ENABLED=1 python manage.py test chat_api.tests --settings=accommodation_project.test_settings`

## Summary
- Total: 161 tests
- V2-mode failures: **79** (75 failures + 4 errors)
- V1-mode failures: 10 (pre-existing, present regardless of v2 flag)
- V2 attributable gap: ~69 tests

## Failure groups

### G1 — Area canonicalization (~12 tests)
V2 returns normalized area like `"quan 3"` instead of canonical `"Quận 3"`.

- `test_compact_hcm_district_names_recommend_partially` (binhthanh, govap)
- `test_thu_duc_compact_recommends_partially_without_user_action`
- `test_da_lat_full_from_no_accent_text`
- `test_q5_short_alias_extracts_wifi_and_guest_without_confirmation`
- `test_follow_up_area_change_understands_spoken_district_number`
- `test_supported_new_fallback_location_can_recommend_partially`
- `test_context_slots_keep_area_for_follow_up_answers`
- `test_partial_area_response_keeps_confirm_table_for_chat_ui`
- `test_soft_filter_area_mode_keeps_budget_and_people`
- `test_popular_unsupported_locations_are_not_unresolved` (Vung Tau, Mũi Né)
- `test_multi_turn_type_update_keeps_anywhere_and_budget_without_geocoder`

Suspected files:
- `chat_api/nlu/input_classifier_v2.py` — `_detect_area` returns normalized form
- `chat_api/nlu/search_intent_builder.py` — `area=resolved.canonical_area or classification.area_hint`
- `chat_api/adapters/search_intent_to_parse_result.py`

### G2 — Compact aliases (~4 tests, subset of G1)
V2 area matcher doesn't accept compact forms.
- `"binhthanh"` → expected `"Bình Thạnh"`
- `"govap"` → expected `"Gò Vấp"`
- `"thuduc"` → expected `"Thủ Đức"`
- `"q5"` → expected `"Quận 5"`

### G3 — Multi-choice / conflict / ambiguous (~8 tests)
- `test_additional_conflict_and_multiple_choice_cases`
- `test_conflicting_supported_locations_block_recommendation`
- `test_landmark_area_conflict_does_not_recommend`
- `test_multiple_choice_requires_one_area`
- `test_multiple_location_choice_is_not_anywhere`
- `test_multiple_supported_area_choice_blocks_recommendation`
- `test_supported_location_choice_blocks_recommendation`
- `test_multiple_type_choice_does_not_force_preferred_type`

### G4 — City-center mode (~3 tests)
V2 has no city_center strategy.
- `test_city_center_rejects_cafe_geocoder_candidate`
- `test_city_center_short_phrases_do_not_geocode_raw_center`
- `test_city_center_typo_is_semantic_location_not_poi`

### G5 — Hotel/resort/accommodation name (~6 tests)
- `test_resort_is_extracted_for_business_logic` (3 subtests — errors not failures)
- `test_near_rex_hotel_accepts_lodging_poi_from_osm`
- `test_submit_accommodation_name_uses_smart_result`
- `test_negated_optional_priority_is_not_added`

### G6 — POI category / map suggestions (~22 tests)
- `test_ambiguous_generic_museum_returns_map_suggestions`
- `test_ambiguous_university_does_not_autoresolve`
- `test_existing_type_keeps_recommendation_for_ambiguous_university`
- `test_amenity_plus_clear_area_keeps_only_area_location`
- `test_generic_airport_needs_clarification_without_geocoder`
- `test_lang_dai_hoc_does_not_autopick_cafe`
- `test_near_hcm_history_museum_accepts_high_similarity_osm_result`
- `test_required_mixed_poi_type_and_amenity` (error)
- `test_required_near_bui_vien_uses_geocoder_or_cache`
- `test_required_poi_noun_does_not_collapse_to_area`
- `test_required_radius_parses_near_anchor_with_amenity`
- `test_required_standalone_pois_resolve_as_near_anchor` (4 subtests)
- `test_required_unknown_poi_does_not_invent_location`
- `test_selected_map_candidate_context_changes_to_new_place`
- `test_soft_filter_far_map_clusters_asks_user_to_choose_candidate`
- `test_soft_filter_near_bitexco_uses_map_api_result`
- `test_soft_filter_near_suoi_tien_uses_local_reference`
- `test_pending_unresolved_anchor_is_not_dropped_when_user_adds_type`
- `test_required_new_location_candidate_does_not_fallback_to_context`
- `test_unresolved_near_landmark_blocks_recommendation`

### G7 — Off-topic / greeting / submit gating (~9 tests)
- `test_greeting_gets_friendly_chatbot_reply_without_recommendation`
- `test_greeting_with_context_keeps_slots_but_does_not_submit`
- `test_off_topic_does_not_ask_mechanical_area_question`
- `test_submit_off_topic_does_not_create_preference`
- `test_submit_greeting_returns_bot_message_without_creating_preference`
- `test_submit_ambiguous_location_without_filters_disables_action`
- `test_submit_location_only_airport_creates_recommendation_action`
- `test_submit_partial_creates_preference_with_recorded_defaults`
- `test_browser_geolocation_is_user_location_origin`

### G8 — Multi-turn / follow-up / confirmation (~9 tests)
- `test_bare_number_follow_up_can_complete_confirmation`
- `test_bare_number_follow_up_sets_missing_guest_count`
- `test_add_more_merges_current_slots_and_lists`
- `test_missing_trip_days_blocks_confirmation`
- `test_ready_result_requires_confirmation_table`
- `test_api_chat_parse_accepts_current_slots_alias`
- `test_api_chat_parse_alias_works`
- `test_auto_strategy_skips_hf_for_follow_up_question`
- `test_auto_strategy_skips_hf_when_rule_result_is_enough`

### G9 — Pre-existing v1 failures (10 tests, not v2-caused)
Visible regardless of `CHAT_PIPELINE_V2_ENABLED`. Out of scope for this v2 push.
- `test_amenity_plus_clear_area_keeps_only_area_location`
- `test_browser_geolocation_is_user_location_origin`
- `test_core_slots_for_common_mixed_language_queries` (An Giang near beach)
- `test_required_standalone_pois_resolve_as_near_anchor` (Bình Quới 1)
- `test_resolve_location_fuzzy_handles_short_district_alias_with_other_slots`
- `test_resolve_location_fuzzy_handles_thu_duc_with_other_slots`
- `test_resolve_location_fuzzy_handles_typo_without_specific_hardcode`
- `test_resolve_location_fuzzy_rejects_unsupported_noise`
- `test_submit_accommodation_name_uses_smart_result`
- `test_typo_quannj7_uses_general_fuzzy_policy`

## Priority

| Order | Group | Why first | Est. impact |
|-------|-------|-----------|-------------|
| 1 | G1 — Area canonicalization | Almost every recommendation path reads area; fix unblocks many tests in G3, G8 | 10–15 tests |
| 2 | G2 — Compact aliases | Small surface, reuses gazetteer alias machinery | 3–5 tests |
| 3 | G3 — Multi-choice / conflict | Pure NLU rules; bridge already supports these statuses | 6–8 tests |
| 4 | G7 — Off-topic gating | Critical for not creating bad preferences | 5–8 tests |
| 5 | G4 — City-center | Localized strategy port from v1 | 3 tests |
| 6 | G5 — Hotel/Resort | Add type aliases | 4–6 tests |
| 7 | G6 — POI / map suggestions | Largest group, most complex; depends on G1 | 15+ tests |
| 8 | G8 — Multi-turn | Last because depends on G1/G3 being right | 5+ tests |

## Test commands
```bash
# V2 mode
CHAT_PIPELINE_V2_ENABLED=1 python manage.py test chat_api.tests --settings=accommodation_project.test_settings

# V1 mode (regression baseline)
CHAT_PIPELINE_V2_ENABLED=0 python manage.py test chat_api.tests --settings=accommodation_project.test_settings
```

## Safety constraints recorded
- `CHAT_PIPELINE_V2_ENABLED` defaults to `0` in `settings.py` — **MUST stay 0**
- No model/migration changes
- No db.sqlite3 changes
- v1 path stays in `parse_user_text` fallback
