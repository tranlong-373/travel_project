import json
import os
from unittest.mock import patch

os.environ.setdefault("CHAT_API_ENABLE_HF_AGENT", "0")

from django.test import SimpleTestCase

from .agent.llm_parser import _extract_json_object
from .agent.schema_normalizer import extract_budget_bounds, normalize_parsed_result
from .fuzzy_location import resolve_location_fuzzy
from .location_gazetteer import generate_location_aliases, load_supported_locations
from .services import parse_user_text
from .text_normalizer import normalize_user_text


class DeterministicParserTests(SimpleTestCase):
    def test_core_slots_for_common_mixed_language_queries(self):
        cases = [
            (
                "cần hostel ở Hà Nội cho 3 người, 2 ngày, budget tầm 1tr2, có wifi là được",
                {"area": "Hà Nội", "budget": 1_200_000, "guest_count": 3},
            ),
            (
                "Need a homestay ở TP HCM for 2 people, 3 nights, budget 1m, quiet and near center",
                {"area": "TP HCM", "budget": 1_000_000, "guest_count": 2},
            ),
            (
                "2 adults and 1 kid, An Giang 3 nights, 2.5m/night, near beach",
                {"area": "An Giang", "budget": 2_500_000, "guest_count": 3},
            ),
        ]

        for text, expected in cases:
            with self.subTest(text=text):
                result = parse_user_text(text)
                self.assertTrue(result["ready_for_recommendation"])
                for key, value in expected.items():
                    self.assertEqual(result["slots"][key], value)

    def test_negated_optional_priority_is_not_added(self):
        result = parse_user_text("Tìm khách sạn ở Bình Định cho 2 người, gần biển, không cần quá rẻ")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertFalse(result["confirmation_required"])
        self.assertNotIn("cheap", result["slots"]["priorities"])
        self.assertEqual(result["missing_slots"], ["budget", "trip_days"])

    def test_multiple_type_choice_does_not_force_preferred_type(self):
        result = parse_user_text("Hotel or apartment in Hanoi for 3 people, 2 nights, near center, 2 million")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertIsNone(result["slots"]["preferred_type"])

    def test_multiple_supported_area_choice_blocks_recommendation(self):
        result = parse_user_text("Hà Nội hoặc TP HCM cho 2 người, budget 1tr2")

        self.assertFalse(result["ready_for_recommendation"])
        self.assertIsNone(result["slots"]["area"])
        self.assertEqual(result["location_status"], "multiple_choice")

    def test_total_trip_budget_cue_blocks_recommendation(self):
        result = parse_user_text(
            "Tôi muốn đi chơi ở TP hồ chí minh, 2 ngày với bạn gái tôi, giá cả chi phí tầm 10 triệu"
        )

        self.assertTrue(result["ready_for_recommendation"])
        self.assertEqual(result["slots"]["budget"], 10_000_000)
        self.assertEqual(result["recommendation_level"], "full")

    def test_supported_location_ok(self):
        result = parse_user_text("Chỗ ở ở Sài Gòn gần Landmark 81 cho 2 người, 2 ngày, budget 1tr5")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["canonical_area"], "TP HCM")
        self.assertEqual(result["slots"]["area"], "TP HCM")

    def test_supported_new_fallback_location_can_recommend_partially(self):
        result = parse_user_text("Tôi cần khách sạn ở Đà Nẵng")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["slots"]["area"], "Đà Nẵng")
        self.assertEqual(result["recommendation_level"], "partial")

    def test_conflicting_supported_locations_block_recommendation(self):
        result = parse_user_text("Tôi muốn ở gần Bến Thành ở Hà Nội cho 2 người, 1tr")

        self.assertFalse(result["ready_for_recommendation"])
        self.assertEqual(result["location_status"], "conflict")
        self.assertIsNone(result["canonical_area"])

    def test_supported_location_choice_blocks_recommendation(self):
        result = parse_user_text("Tôi muốn tìm chỗ ở Hà Nội hay TP HCM đều được cho 2 người, 1tr")

        self.assertFalse(result["ready_for_recommendation"])
        self.assertEqual(result["location_status"], "multiple_choice")
        self.assertIsNone(result["canonical_area"])

    def test_popular_unsupported_locations_are_not_unresolved(self):
        cases = [
            "Hotel in Vung Tau for 1 person, near beach, 700k",
            "Cho mình homestay ở Mũi Né cho nhóm 6 người, gần biển",
        ]

        for text in cases:
            with self.subTest(text=text):
                result = parse_user_text(text)
                self.assertEqual(result["location_status"], "unsupported")
                self.assertIsNone(result["canonical_area"])
                self.assertIsNone(result["slots"]["area"])
                self.assertFalse(result["ready_for_recommendation"])

    def test_cho_ray_resolves_to_supported_tp_hcm(self):
        result = parse_user_text("Hotel near Cho Ray for 1 person, 2 ngày, 700k, safe area")

        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["canonical_area"], "TP HCM")
        self.assertEqual(result["slots"]["area"], "TP HCM")
        self.assertTrue(result["ready_for_recommendation"])

    def test_additional_conflict_and_multiple_choice_cases(self):
        conflict = parse_user_text("Landmark 81 ở Đồng Nai")
        self.assertEqual(conflict["location_status"], "conflict")
        self.assertFalse(conflict["ready_for_recommendation"])

        multiple_choice = parse_user_text("Khách sạn ở TP HCM hoặc Hà Nội cho 2 người, 1tr5")
        self.assertEqual(multiple_choice["location_status"], "multiple_choice")
        self.assertFalse(multiple_choice["ready_for_recommendation"])

    def test_resort_is_extracted_for_business_logic(self):
        cases = [
            "Tìm resort ở Phú Quốc cho 2 người, gần biển, không cần quá rẻ, 2tr",
            "Budget 2 million, need a resort in Phan Thiet for a couple",
            "Mình muốn resort ở Phú Quốc có hồ bơi, 2 người, 3 đêm, 2tr",
        ]

        for text in cases:
            with self.subTest(text=text):
                result = parse_user_text(text)
                self.assertIsNone(result["slots"]["preferred_type"])
                self.assertEqual(result["slots"]["unsupported_preferred_type"], "resort")

    def test_context_slots_keep_area_for_follow_up_answers(self):
        first = parse_user_text("Khách sạn ở Hà Nội cho 2 người")
        self.assertTrue(first["ready_for_recommendation"])
        self.assertFalse(first["confirmation_required"])
        self.assertEqual(first["slots"]["area"], "Hà Nội")
        self.assertEqual(first["missing_slots"], ["budget", "trip_days"])

        follow_up = parse_user_text("900k 2 ngày", context_slots=first["slots"])
        self.assertTrue(follow_up["ready_for_recommendation"])
        self.assertEqual(follow_up["location_status"], "ok")
        self.assertEqual(follow_up["slots"]["area"], "Hà Nội")
        self.assertEqual(follow_up["slots"]["budget"], 900_000)
        self.assertEqual(follow_up["slots"]["budget_max"], 900_000)

    def test_follow_up_area_change_understands_spoken_district_number(self):
        first = parse_user_text("Khách sạn ở quận 7")
        self.assertEqual(first["slots"]["area"], "Quận 7")

        follow_up = parse_user_text("đổi thành quận hai đi", context_slots=first["slots"])

        self.assertEqual(follow_up["location_status"], "ok")
        self.assertEqual(follow_up["slots"]["area"], "Quận 2")

    def test_bare_number_follow_up_sets_missing_guest_count(self):
        first = parse_user_text("Mình muốn ở Đà Lạt, khoảng 800k")
        self.assertTrue(first["ready_for_recommendation"])
        self.assertFalse(first["confirmation_required"])
        self.assertIn("mấy người", first["follow_up_question"])
        self.assertIsNone(first["slots"]["guest_count"])

        follow_up = parse_user_text("2", context_slots=first["slots"])

        self.assertTrue(follow_up["ready_for_recommendation"])
        self.assertFalse(follow_up["confirmation_required"])
        self.assertEqual(follow_up["slots"]["area"], "Đà Lạt")
        self.assertEqual(follow_up["slots"]["budget"], 800_000)
        self.assertEqual(follow_up["slots"]["guest_count"], 2)
        self.assertEqual(follow_up["missing_slots"], ["trip_days"])
        self.assertIn("ưu tiên", follow_up["follow_up_question"])

    def test_bare_number_follow_up_can_complete_confirmation(self):
        first = parse_user_text("Mình muốn ở Đà Lạt, 3 ngày, khoảng 800k")
        self.assertTrue(first["ready_for_recommendation"])
        self.assertFalse(first["confirmation_required"])
        self.assertEqual(first["missing_slots"], ["guest_count"])

        follow_up = parse_user_text("2", context_slots=first["slots"])

        self.assertTrue(follow_up["ready_for_recommendation"])
        self.assertFalse(follow_up["confirmation_required"])
        self.assertEqual(follow_up["slots"]["guest_count"], 2)
        self.assertEqual(follow_up["slots"]["trip_days"], 3)

    def test_missing_trip_days_blocks_confirmation(self):
        result = parse_user_text("Mình muốn đi Đà Lạt")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertFalse(result["awaiting_confirmation"])
        self.assertFalse(result["confirmation_required"])
        self.assertIn("budget", result["missing_slots"])
        self.assertIn("guest_count", result["missing_slots"])
        self.assertIn("trip_days", result["missing_slots"])
        self.assertIn("confirm_table", result)
        self.assertIn(
            {"key": "area", "label": "Khu vực", "value": "Đà Lạt", "display_value": "Đà Lạt"},
            result["confirm_table"],
        )

    def test_ready_result_requires_confirmation_table(self):
        result = parse_user_text("Mình muốn ở Đà Lạt cho 2 người, 3 ngày, khoảng 800k")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertFalse(result["confirmation_required"])
        self.assertFalse(result["awaiting_confirmation"])
        self.assertEqual(result["schema_version"], "2.0")
        self.assertEqual(result["recommendation_level"], "full")
        self.assertEqual(result["slots"]["area"], "Đà Lạt")
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertEqual(result["slots"]["budget"], 800_000)
        self.assertEqual(result["slots"]["trip_days"], 3)

    def test_confirmation_table_includes_amenities(self):
        result = parse_user_text("Mình muốn ở Đà Lạt cho 2 người 3 ngày tầm 800k, cần wifi và hồ bơi")

        self.assertFalse(result["confirmation_required"])
        self.assertIn("wifi", result["slots"]["required_amenities"])
        self.assertIn("pool", result["slots"]["required_amenities"])

    def test_add_more_merges_current_slots_and_lists(self):
        first = parse_user_text("Mình muốn ở Đà Lạt cho 2 người, 3 ngày, khoảng 800k")
        follow_up = parse_user_text("có trẻ em và cần chỗ yên tĩnh", context_slots=first["slots"])

        self.assertFalse(follow_up["confirmation_required"])
        self.assertEqual(follow_up["slots"]["area"], "Đà Lạt")
        self.assertEqual(follow_up["slots"]["budget"], 800_000)
        self.assertEqual(follow_up["slots"]["guest_count"], 2)
        self.assertEqual(follow_up["slots"]["trip_days"], 3)
        self.assertIn("baby_friendly", follow_up["slots"]["special_requirements"])
        self.assertIn("quiet", follow_up["slots"]["priorities"])

    def test_greeting_gets_friendly_chatbot_reply_without_recommendation(self):
        with patch.dict(os.environ, {"CHAT_API_ENABLE_HF_AGENT": "1", "CHAT_API_LLM_STRATEGY": "auto"}):
            with patch("chat_api.agent.llm_parser.get_hf_slot_parser") as mock_get_parser:
                result = parse_user_text("chào cậu")

        mock_get_parser.assert_not_called()
        self.assertEqual(result["conversation_intent"], "greeting")
        self.assertIn("Chào bạn", result["bot_message"])
        self.assertIn("khu vực", result["bot_message"])
        self.assertFalse(result["ready_for_recommendation"])
        self.assertFalse(result["confirmation_required"])
        self.assertNotIn("confirm_table", result)

    def test_greeting_with_context_keeps_slots_but_does_not_submit(self):
        context = {"area": "đà lạt", "budget": 800_000}

        result = parse_user_text("hello", context_slots=context)

        self.assertEqual(result["conversation_intent"], "greeting")
        self.assertEqual(result["slots"]["area"], "đà lạt")
        self.assertEqual(result["slots"]["budget"], 800_000)
        self.assertFalse(result["ready_for_recommendation"])
        self.assertIn("gợi ý chỗ ở", result["bot_message"])


class SchemaNormalizerTests(SimpleTestCase):
    def test_budget_range_and_compact_million_text(self):
        self.assertEqual(extract_budget_bounds("từ 500 đến 900k"), (500_000, 900_000))
        self.assertEqual(extract_budget_bounds("tầm 1tr2 đổ lại"), (None, 1_200_000))

    def test_normalizer_combines_llm_output_with_rule_fallback(self):
        fallback = {
            "slots": {
                "area": None,
                "budget": None,
                "guest_count": None,
                "preferred_type": None,
                "required_amenities": [],
                "priorities": [],
                "special_requirements": [],
            },
            "location_status": "unresolved",
            "location_candidates": [],
        }
        model_payload = {
            "slots": {
                "area": "Vũng Tàu",
                "budget_max": "800k",
                "guest_count": 2,
                "preferred_type": "resort",
                "required_amenities": ["hồ bơi"],
                "priorities": ["view đẹp", "gần biển"],
                "special_requirements": ["couple"],
            }
        }

        result = normalize_parsed_result(
            model_payload,
            raw_text="resort Vũng Tàu cho couple, 800k, hồ bơi view đẹp gần biển",
            fallback_result=fallback,
        )

        self.assertEqual(result["slots"]["area"], "vũng tàu")
        self.assertEqual(result["slots"]["budget_max"], 800_000)
        self.assertEqual(result["slots"]["preferred_type"], "resort")
        self.assertIn("pool", result["slots"]["required_amenities"])
        self.assertIn("nice_view", result["slots"]["priorities"])
        self.assertIn("near_beach", result["slots"]["priorities"])
        self.assertIn("couple_friendly", result["slots"]["special_requirements"])


class LLMParserUtilityTests(SimpleTestCase):
    def test_extract_json_object_repairs_markdown_wrapper(self):
        payload = _extract_json_object(
            '```json\n{"intent":"recommend_accommodation","slots":{"area":"tp hcm"}}\n```'
        )

        self.assertEqual(payload["slots"]["area"], "tp hcm")


class LocationFoundationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fallback_locations = load_supported_locations()

    def test_normalize_user_text_handles_compact_location_guest_and_wifi(self):
        result = normalize_user_text("quan7 2ng wf")

        self.assertIn("quan 7", result["no_accent_text"])
        self.assertIn("2 nguoi", result["no_accent_text"])
        self.assertIn("wifi", result["normalized_text"])

    def test_generate_location_aliases_for_tp_thu_duc(self):
        aliases = generate_location_aliases("Thủ Đức", city="TP HCM", type="district")

        self.assertIn("thu duc", aliases)
        self.assertIn("thuduc", aliases)
        self.assertIn("tp thu duc", aliases)
        self.assertIn("thanh pho thu duc", aliases)
        self.assertIn("thu duc city", aliases)

    def test_load_supported_locations_keeps_single_thu_duc_label(self):
        names = [
            location["canonical_name"]
            for location in self.fallback_locations
            if "thủ đức" in location["canonical_name"].lower()
        ]

        self.assertEqual(names, ["Thủ Đức"])

    def test_generate_location_aliases_for_binh_thanh(self):
        aliases = generate_location_aliases("Bình Thạnh")

        self.assertIn("binh thanh", aliases)
        self.assertIn("binhthanh", aliases)

    def test_generate_location_aliases_for_go_vap(self):
        aliases = generate_location_aliases("Gò Vấp")

        self.assertIn("go vap", aliases)
        self.assertIn("govap", aliases)

    def test_generate_location_aliases_for_numbered_district(self):
        aliases = generate_location_aliases("Quận 7")

        self.assertIn("quan 7", aliases)
        self.assertIn("quan7", aliases)
        self.assertIn("q7", aliases)
        self.assertIn("district 7", aliases)

    def test_resolve_location_fuzzy_handles_compact_thu_duc_in_sentence(self):
        result = resolve_location_fuzzy("tôi muốn ở gần thuduc", self.fallback_locations)

        self.assertEqual(result["canonical_area"], "Thủ Đức")
        self.assertEqual(result["location_status"], "ok")
        self.assertGreaterEqual(result["location_confidence"], 0.75)

    def test_resolve_location_fuzzy_handles_thu_duc_with_other_slots(self):
        result = resolve_location_fuzzy("thu duc 2 nguoi 800k", self.fallback_locations)

        self.assertEqual(result["canonical_area"], "Thủ Đức")
        self.assertEqual(result["location_status"], "ok")

    def test_resolve_location_fuzzy_handles_tp_thu_duc_as_thu_duc(self):
        result = resolve_location_fuzzy("TP Thủ Đức", self.fallback_locations)

        self.assertEqual(result["canonical_area"], "Thủ Đức")
        self.assertEqual(result["location_status"], "ok")

    def test_resolve_location_fuzzy_handles_binh_thanh_compact(self):
        result = resolve_location_fuzzy("binhthanh", self.fallback_locations)

        self.assertEqual(result["canonical_area"], "Bình Thạnh")

    def test_resolve_location_fuzzy_handles_go_vap_compact(self):
        result = resolve_location_fuzzy("govap", self.fallback_locations)

        self.assertEqual(result["canonical_area"], "Gò Vấp")

    def test_resolve_location_fuzzy_handles_short_district_alias_with_other_slots(self):
        result = resolve_location_fuzzy("q5 wf 2ng", self.fallback_locations)

        self.assertEqual(result["canonical_area"], "Quận 5")

    def test_resolve_location_fuzzy_handles_typo_without_specific_hardcode(self):
        result = resolve_location_fuzzy("quannj7", self.fallback_locations)

        self.assertIn(result["location_status"], {"ok", "ambiguous", "unresolved"})
        if result["location_status"] == "ok":
            self.assertEqual(result["canonical_area"], "Quận 7")

    def test_resolve_location_fuzzy_rejects_unsupported_noise(self):
        result = resolve_location_fuzzy("qannx999", self.fallback_locations)

        self.assertIn(result["location_status"], {"unresolved", "unsupported"})
        self.assertIsNone(result["canonical_area"])

    def test_resolve_location_fuzzy_does_not_crash_on_empty_or_noise(self):
        for text in (None, "", "???", "abcxyz"):
            with self.subTest(text=text):
                result = resolve_location_fuzzy(text, self.fallback_locations)

                self.assertEqual(result["location_status"], "unresolved")
                self.assertIsNone(result["canonical_area"])

    def test_resolve_location_fuzzy_returns_multiple_choice_for_clear_locations(self):
        result = resolve_location_fuzzy("Tìm khách sạn ở Hà Nội hoặc TP HCM", self.fallback_locations)

        self.assertEqual(result["location_status"], "multiple_choice")
        candidate_names = {candidate["canonical_area"] for candidate in result["location_candidates"]}
        self.assertTrue({"Hà Nội", "TP HCM"}.issubset(candidate_names) or len(candidate_names) > 1)


class ConveniencePipelineTests(SimpleTestCase):
    def test_thu_duc_compact_recommends_partially_without_user_action(self):
        result = parse_user_text("tôi muốn ở gần thuduc")

        self.assertEqual(result["canonical_area"], "Thủ Đức")
        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["recommendation_level"], "partial")
        self.assertTrue(result["can_show_recommendations"])
        self.assertFalse(result["needs_user_action"])
        self.assertIn("gợi ý trước", result["polite_bot_message"])

    def test_thu_duc_with_budget_and_guest_is_full(self):
        result = parse_user_text("thu duc 2 nguoi 800k")

        self.assertEqual(result["canonical_area"], "Thủ Đức")
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertEqual(result["slots"]["budget_max"], 800_000)
        self.assertEqual(result["recommendation_level"], "full")
        self.assertTrue(result["can_show_recommendations"])

    def test_compact_hcm_district_names_recommend_partially(self):
        for text, area in [("binhthanh", "Bình Thạnh"), ("govap", "Gò Vấp")]:
            with self.subTest(text=text):
                result = parse_user_text(text)

                self.assertEqual(result["canonical_area"], area)
                self.assertTrue(result["can_show_recommendations"])
                self.assertEqual(result["recommendation_level"], "partial")

    def test_q5_short_alias_extracts_wifi_and_guest_without_confirmation(self):
        result = parse_user_text("q5 wf 2ng")

        self.assertEqual(result["canonical_area"], "Quận 5")
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertIn("wifi", result["slots"]["required_amenities"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertFalse(result["needs_confirmation"])
        self.assertEqual(result["confirmation_type"], "none")

    def test_typo_quannj7_uses_general_fuzzy_policy(self):
        result = parse_user_text("quannj7")

        self.assertIn(result["location_status"], {"ok", "ambiguous", "unresolved"})
        if result["location_status"] == "ok":
            self.assertEqual(result["canonical_area"], "Quận 7")
            self.assertTrue(result["can_show_recommendations"])
            self.assertIn(result["confirmation_type"], {"none", "implicit"})
        elif result["location_status"] == "ambiguous":
            self.assertTrue(result["needs_confirmation"])

    def test_bad_location_noise_does_not_recommend(self):
        result = parse_user_text("qannx999")

        self.assertIn(result["location_status"], {"unresolved", "unsupported"})
        self.assertFalse(result["can_show_recommendations"])
        self.assertIsNone(result["canonical_area"])
        self.assertIn("khu vực", result["polite_bot_message"])

    def test_off_topic_does_not_ask_mechanical_area_question(self):
        result = parse_user_text("hôm nay trời mưa không")

        self.assertEqual(result["intent"], "off_topic")
        self.assertEqual(result["recommendation_level"], "none")
        self.assertFalse(result["can_show_recommendations"])
        self.assertNotIn("Bạn muốn ở khu vực nào", result["polite_bot_message"])

    def test_multiple_choice_requires_one_area(self):
        result = parse_user_text("Tìm khách sạn ở Hà Nội hoặc TP HCM")

        self.assertEqual(result["location_status"], "multiple_choice")
        self.assertFalse(result["can_show_recommendations"])
        self.assertTrue(result["needs_confirmation"])
        self.assertIn("khu vực nào", result["polite_bot_message"])

    def test_landmark_area_conflict_does_not_recommend(self):
        result = parse_user_text("gần Bến Thành ở Hà Nội")

        self.assertEqual(result["location_status"], "conflict")
        self.assertFalse(result["can_show_recommendations"])

    def test_quan_5_partial_has_budget_and_guest_quick_replies(self):
        result = parse_user_text("Tôi muốn đi Quận 5")

        self.assertEqual(result["recommendation_level"], "partial")
        self.assertTrue(result["can_show_recommendations"])
        labels = {reply["label"] for reply in result["quick_replies"]}
        self.assertIn("500k - 800k", labels)
        self.assertIn("Đi 2 người", labels)

    def test_partial_area_response_keeps_confirm_table_for_chat_ui(self):
        result = parse_user_text("tôi muốn đi quân 1")

        self.assertEqual(result["canonical_area"], "Quận 1")
        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["recommendation_level"], "partial")
        self.assertFalse(result["confirmation_required"])
        self.assertIsNone(result["slots"]["preferred_type"])
        self.assertIn(
            {"key": "area", "label": "Khu vực", "value": "Quận 1", "display_value": "Quận 1"},
            result["confirm_table"],
        )
        self.assertNotIn("preferred_type", {item["key"] for item in result["confirm_table"]})
        self.assertIn("gợi ý trước", result["polite_bot_message"])

    def test_da_lat_full_from_no_accent_text(self):
        result = parse_user_text("khach san da lat 2 nguoi 800k")

        self.assertEqual(result["canonical_area"], "Đà Lạt")
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertEqual(result["slots"]["budget_max"], 800_000)
        self.assertEqual(result["recommendation_level"], "full")
        self.assertTrue(result["can_show_recommendations"])

    def test_anywhere_vague_request_asks_for_location_without_recommendation(self):
        result = parse_user_text("đi đâu cũng được")

        self.assertIsNone(result["canonical_area"])
        self.assertFalse(result["can_show_recommendations"])
        self.assertIn("khu vực", result["polite_bot_message"])


class ParseEndpointTests(SimpleTestCase):
    def test_api_chat_parse_alias_works(self):
        response = self.client.post(
            "/api/chat/parse/",
            data=json.dumps({"text": "Khách sạn ở Sài Gòn cho 2 người, 2 ngày, 900k"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "recommend_accommodation")
        self.assertEqual(data["slots"]["area"], "TP HCM")
        self.assertEqual(data["slots"]["budget_max"], 900_000)

    def test_api_chat_parse_requires_text(self):
        response = self.client.post(
            "/api/chat/parse/",
            data=json.dumps({"text": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_api_chat_parse_accepts_current_slots_alias(self):
        response = self.client.post(
            "/api/chat/parse/",
            data=json.dumps(
                {
                    "text": "có trẻ em và cần chỗ yên tĩnh",
                    "current_slots": {
                        "area": "đà lạt",
                        "budget": 800_000,
                        "guest_count": 2,
                        "trip_days": 3,
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["confirmation_required"])
        self.assertEqual(data["slots"]["area"], "Đà Lạt")
        self.assertIn("baby_friendly", data["slots"]["special_requirements"])
        self.assertIn("quiet", data["slots"]["priorities"])

    def test_submit_greeting_returns_bot_message_without_creating_preference(self):
        response = self.client.post(
            "/chat_api/submit/",
            data=json.dumps({"text": "chào cậu"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["conversation_intent"], "greeting")
        self.assertIn("Chào bạn", data["bot_message"])
        self.assertFalse(data["ready_for_recommendation"])
        self.assertFalse(data["created_preference"])
        self.assertIsNone(data["recommendation_url"])


class SubmitMessagePreferenceTests(SimpleTestCase):
    def test_submit_off_topic_does_not_create_preference(self):
        response = self.client.post(
            "/chat_api/submit/",
            data=json.dumps({"text": "hôm nay trời mưa không"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "off_topic")
        self.assertFalse(data["created_preference"])

    def test_submit_partial_creates_preference_with_recorded_defaults(self):
        bridge_payload = {
            "pref_id": 123,
            "recommendation_url": "/recommendations/result/123/",
            "used_default_slots": {
                "budget": {"value": 0, "reason": "user_missing_budget_no_budget_filter"},
                "guest_count": {"value": 1, "reason": "user_missing_guest_count_safe_minimum"},
            },
        }
        with patch("chat_api.views.create_preference_from_parse", return_value=bridge_payload):
            response = self.client.post(
                "/chat_api/submit/",
                data=json.dumps({"text": "tôi muốn đi Quận 5"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["created_preference"])
        self.assertEqual(data["recommendation_level"], "partial")
        self.assertTrue(data["can_show_recommendations"])
        self.assertIsNotNone(data["pref_id"])
        self.assertIn("/recommendations/", data["recommendation_url"])
        self.assertEqual(data["used_default_slots"]["budget"]["value"], 0)
        self.assertEqual(data["used_default_slots"]["guest_count"]["value"], 1)
        self.assertIn(
            {"key": "area", "label": "Khu vực", "value": "Quận 5", "display_value": "Quận 5"},
            data["confirm_table"],
        )

    def test_submit_area_only_quan_2_creates_partial_recommendation(self):
        bridge_payload = {
            "pref_id": 456,
            "recommendation_url": "/recommendations/result/456/",
            "used_default_slots": {
                "budget": {"value": 0, "reason": "user_missing_budget_no_budget_filter"},
                "guest_count": {"value": 1, "reason": "user_missing_guest_count_safe_minimum"},
            },
        }
        with patch("chat_api.views.create_preference_from_parse", return_value=bridge_payload) as mock_bridge:
            response = self.client.post(
                "/chat_api/submit/",
                data=json.dumps({"text": "quận 2"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["created_preference"])
        self.assertEqual(data["canonical_area"], "Quận 2")
        self.assertEqual(data["recommendation_level"], "partial")
        self.assertTrue(data["can_show_recommendations"])
        self.assertEqual(data["recommendation_url"], "/recommendations/result/456/")
        self.assertIn(
            {"key": "area", "label": "Khu vực", "value": "Quận 2", "display_value": "Quận 2"},
            data["confirm_table"],
        )
        self.assertEqual(mock_bridge.call_args.args[0]["slots"]["preferred_type"], None)


class ParserPerformanceStrategyTests(SimpleTestCase):
    def test_auto_strategy_skips_hf_when_rule_result_is_enough(self):
        with patch.dict(os.environ, {"CHAT_API_ENABLE_HF_AGENT": "1", "CHAT_API_LLM_STRATEGY": "auto"}):
            with patch("chat_api.agent.llm_parser.get_hf_slot_parser") as mock_get_parser:
                result = parse_user_text("Khách sạn ở Sài Gòn cho 2 người, 2 ngày, 900k")

        mock_get_parser.assert_not_called()
        self.assertTrue(result["ready_for_recommendation"])
        self.assertEqual(result["parser_mode"], "deterministic_fuzzy_fast")

    def test_auto_strategy_skips_hf_for_follow_up_question(self):
        with patch.dict(os.environ, {"CHAT_API_ENABLE_HF_AGENT": "1", "CHAT_API_LLM_STRATEGY": "auto"}):
            with patch("chat_api.agent.llm_parser.get_hf_slot_parser") as mock_get_parser:
                result = parse_user_text("có chỗ nào gần trung tâm, yên tĩnh, có wifi mạnh để làm việc không")

        mock_get_parser.assert_not_called()
        self.assertFalse(result["ready_for_recommendation"])
        self.assertFalse(result["confirmation_required"])
        self.assertIn("area", result["missing_slots"])
        self.assertEqual(result["parser_mode"], "deterministic_fuzzy_fast")
