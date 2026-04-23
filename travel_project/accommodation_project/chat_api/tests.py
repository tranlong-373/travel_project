import json
import os
from unittest.mock import patch

os.environ.setdefault("CHAT_API_ENABLE_HF_AGENT", "0")

from django.test import SimpleTestCase

from .agent.llm_parser import _extract_json_object
from .agent.schema_normalizer import extract_budget_bounds, normalize_parsed_result
from .services import parse_user_text


class DeterministicParserTests(SimpleTestCase):
    def test_core_slots_for_common_mixed_language_queries(self):
        cases = [
            (
                "cần hostel ở Hà Nội cho 3 người, budget tầm 1tr2, có wifi là được",
                {"area": "hà nội", "budget": 1_200_000, "guest_count": 3},
            ),
            (
                "Need a homestay ở TP HCM for 2 people, budget 1m, quiet and near center",
                {"area": "tp hcm", "budget": 1_000_000, "guest_count": 2},
            ),
            (
                "2 adults and 1 kid, An Giang 3 nights, 2.5m/night, near beach",
                {"area": "an giang", "budget": 2_500_000, "guest_count": 3},
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

        self.assertFalse(result["ready_for_recommendation"])
        self.assertNotIn("cheap", result["slots"]["priorities"])
        self.assertEqual(result["missing_slots"], ["budget"])

    def test_multiple_type_choice_does_not_force_preferred_type(self):
        result = parse_user_text("Hotel or apartment in Hanoi for 3 people, near center, 2 million")

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

        self.assertFalse(result["ready_for_recommendation"])
        self.assertEqual(result["slots"]["budget"], 10_000_000)
        self.assertIn("mỗi đêm", result["follow_up_question"])

    def test_supported_location_ok(self):
        result = parse_user_text("Chỗ ở ở Sài Gòn gần Landmark 81 cho 2 người, budget 1tr5")

        self.assertTrue(result["ready_for_recommendation"])
        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["canonical_area"], "tp hcm")
        self.assertEqual(result["slots"]["area"], "tp hcm")

    def test_unsupported_location_blocks_recommendation(self):
        result = parse_user_text("Tôi cần khách sạn ở Đà Nẵng")

        self.assertFalse(result["ready_for_recommendation"])
        self.assertEqual(result["location_status"], "unsupported")
        self.assertEqual(result["slots"]["area"], "đà nẵng")

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
            "Need a work-friendly hotel in Can Tho for 1 person, 3 nights, 900k",
            "Cho mình homestay ở Mũi Né cho nhóm 6 người, gần biển",
        ]

        for text in cases:
            with self.subTest(text=text):
                result = parse_user_text(text)
                self.assertEqual(result["location_status"], "unsupported")
                self.assertIsNone(result["canonical_area"])
                self.assertIsNotNone(result["slots"]["area"])
                self.assertFalse(result["ready_for_recommendation"])

    def test_cho_ray_resolves_to_supported_tp_hcm(self):
        result = parse_user_text("Hotel near Cho Ray for 1 person, 700k, safe area")

        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["canonical_area"], "tp hcm")
        self.assertEqual(result["slots"]["area"], "tp hcm")
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
                self.assertEqual(result["slots"]["preferred_type"], "resort")

    def test_context_slots_keep_area_for_follow_up_answers(self):
        first = parse_user_text("Khách sạn ở Hà Nội cho 2 người")
        self.assertFalse(first["ready_for_recommendation"])
        self.assertEqual(first["slots"]["area"], "hà nội")

        follow_up = parse_user_text("900k", context_slots=first["slots"])
        self.assertTrue(follow_up["ready_for_recommendation"])
        self.assertEqual(follow_up["location_status"], "ok")
        self.assertEqual(follow_up["slots"]["area"], "hà nội")
        self.assertEqual(follow_up["slots"]["budget"], 900_000)
        self.assertEqual(follow_up["slots"]["budget_max"], 900_000)


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


class ParseEndpointTests(SimpleTestCase):
    def test_api_chat_parse_alias_works(self):
        response = self.client.post(
            "/api/chat/parse/",
            data=json.dumps({"text": "Khách sạn ở Sài Gòn cho 2 người, 900k"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "recommend_accommodation")
        self.assertEqual(data["slots"]["area"], "tp hcm")
        self.assertEqual(data["slots"]["budget_max"], 900_000)

    def test_api_chat_parse_requires_text(self):
        response = self.client.post(
            "/api/chat/parse/",
            data=json.dumps({"text": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)


class ParserPerformanceStrategyTests(SimpleTestCase):
    def test_auto_strategy_skips_hf_when_rule_result_is_enough(self):
        with patch.dict(os.environ, {"CHAT_API_ENABLE_HF_AGENT": "1", "CHAT_API_LLM_STRATEGY": "auto"}):
            with patch("chat_api.agent.llm_parser.get_hf_slot_parser") as mock_get_parser:
                result = parse_user_text("Khách sạn ở Sài Gòn cho 2 người, 900k")

        mock_get_parser.assert_not_called()
        self.assertTrue(result["ready_for_recommendation"])
        self.assertEqual(result["parser_mode"], "hybrid_rule_fast")

    def test_auto_strategy_skips_hf_for_follow_up_question(self):
        with patch.dict(os.environ, {"CHAT_API_ENABLE_HF_AGENT": "1", "CHAT_API_LLM_STRATEGY": "auto"}):
            with patch("chat_api.agent.llm_parser.get_hf_slot_parser") as mock_get_parser:
                result = parse_user_text("có chỗ nào gần trung tâm, yên tĩnh, có wifi mạnh để làm việc không")

        mock_get_parser.assert_not_called()
        self.assertFalse(result["ready_for_recommendation"])
        self.assertIn("area", result["missing_slots"])
        self.assertEqual(result["parser_mode"], "hybrid_rule_fast")
