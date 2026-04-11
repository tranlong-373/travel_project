from django.test import SimpleTestCase

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
        self.assertIsNone(result["slots"]["area"])

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
                self.assertIsNone(result["slots"]["area"])
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

    def test_resort_stays_null_until_downstream_supports_it(self):
        cases = [
            "Tìm resort ở Phú Quốc cho 2 người, gần biển, không cần quá rẻ",
            "Budget 2 million, need a resort in Phan Thiet for a couple",
            "Mình muốn resort ở Phú Quốc có hồ bơi, 2 người, 3 đêm",
        ]

        for text in cases:
            with self.subTest(text=text):
                result = parse_user_text(text)
                self.assertIsNone(result["slots"]["preferred_type"])

    def test_context_slots_keep_area_for_follow_up_answers(self):
        first = parse_user_text("Khách sạn ở Hà Nội cho 2 người")
        self.assertFalse(first["ready_for_recommendation"])
        self.assertEqual(first["slots"]["area"], "hà nội")

        follow_up = parse_user_text("900k", context_slots=first["slots"])
        self.assertTrue(follow_up["ready_for_recommendation"])
        self.assertEqual(follow_up["location_status"], "ok")
        self.assertEqual(follow_up["slots"]["area"], "hà nội")
        self.assertEqual(follow_up["slots"]["budget"], 900_000)
