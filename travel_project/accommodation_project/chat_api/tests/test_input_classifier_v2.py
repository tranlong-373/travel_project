"""
Unit tests for InputClassifierV2.classify_v2().

Mandatory cases (spec):
  1.  "có parking"                                    → amenity_only, NOT location
  2.  "có chỗ đậu xe"                                 → amenity_only
  3.  "1 Sư Vạn Hạnh, Phường 9, Quận 5, TP HCM"     → specific_address, full address kept
  4.  "gần Landmark 81"                               → landmark_or_poi / near_anchor signal
  5.  "gần quán cafe ở Quận 5"                        → generic_poi_in_area
  6.  "Rex Hotel"                                     → hotel_name
  7.  "Quận 3"                                        → area
  8.  "khách sạn gần Nhà thờ Đức Bà dưới 1tr2 cho 2 người có wifi" → mixed_search

Run:  python manage.py test chat_api.tests.test_input_classifier_v2
"""
from django.test import SimpleTestCase

from chat_api.nlu.input_classifier_v2 import ClassificationResult, classify_v2


class TestMandatoryCases(SimpleTestCase):
    """8 mandatory classification cases from spec."""

    # ── 1 & 2. amenity_only — must NOT be classified as location ──────────────

    def test_co_parking_is_amenity_only(self):
        result = classify_v2("có parking")
        self.assertEqual(result.input_kind, "amenity_only")
        self.assertIn("parking", result.amenity_terms)

    def test_co_parking_is_not_location(self):
        result = classify_v2("có parking")
        self.assertNotIn(result.input_kind, {"area", "landmark_or_poi", "specific_address"})

    def test_co_cho_dau_xe_is_amenity_only(self):
        result = classify_v2("có chỗ đậu xe")
        self.assertEqual(result.input_kind, "amenity_only")
        self.assertIn("parking", result.amenity_terms)

    def test_co_cho_dau_xe_is_not_location(self):
        result = classify_v2("có chỗ đậu xe")
        self.assertNotIn(result.input_kind, {"area", "landmark_or_poi", "specific_address"})

    # ── 3. specific_address — full address preserved ───────────────────────────

    def test_specific_address_classified(self):
        result = classify_v2("1 Sư Vạn Hạnh, Phường 9, Quận 5, TP HCM")
        self.assertEqual(result.input_kind, "specific_address")

    def test_specific_address_location_phrase_not_empty(self):
        result = classify_v2("1 Sư Vạn Hạnh, Phường 9, Quận 5, TP HCM")
        self.assertIsNotNone(result.location_phrase)
        self.assertGreater(len(result.location_phrase or ""), 0)

    def test_specific_address_confidence_high(self):
        result = classify_v2("1 Sư Vạn Hạnh, Phường 9, Quận 5, TP HCM")
        self.assertGreater(result.confidence, 0.80)

    # ── 4. landmark_or_poi — "gần Landmark 81" ────────────────────────────────

    def test_near_landmark_81(self):
        result = classify_v2("gần Landmark 81")
        self.assertEqual(result.input_kind, "landmark_or_poi")

    def test_near_landmark_81_location_phrase_captured(self):
        result = classify_v2("gần Landmark 81")
        self.assertIsNotNone(result.location_phrase)

    def test_near_landmark_81_confidence(self):
        result = classify_v2("gần Landmark 81")
        self.assertGreater(result.confidence, 0.70)

    # ── 5. generic_poi_in_area — "gần quán cafe ở Quận 5" ────────────────────

    def test_near_cafe_in_district_5(self):
        result = classify_v2("gần quán cafe ở Quận 5")
        self.assertEqual(result.input_kind, "generic_poi_in_area")

    def test_near_cafe_in_district_5_area_hint(self):
        result = classify_v2("gần quán cafe ở Quận 5")
        self.assertIsNotNone(result.area_hint)

    def test_near_cafe_in_district_5_confidence(self):
        result = classify_v2("gần quán cafe ở Quận 5")
        self.assertGreater(result.confidence, 0.80)

    # ── 6. hotel_name — "Rex Hotel" ───────────────────────────────────────────

    def test_rex_hotel_is_hotel_name(self):
        result = classify_v2("Rex Hotel")
        self.assertEqual(result.input_kind, "hotel_name")

    def test_rex_hotel_name_field_set(self):
        result = classify_v2("Rex Hotel")
        self.assertIsNotNone(result.hotel_name)

    # ── 7. area — "Quận 3" ────────────────────────────────────────────────────

    def test_district_3_is_area(self):
        result = classify_v2("Quận 3")
        self.assertEqual(result.input_kind, "area")

    def test_district_3_area_hint(self):
        result = classify_v2("Quận 3")
        self.assertIsNotNone(result.area_hint)
        self.assertIn("3", result.area_hint or "")

    def test_district_3_location_phrase_set(self):
        result = classify_v2("Quận 3")
        self.assertIsNotNone(result.location_phrase)

    # ── 8. mixed_search — full compound query ─────────────────────────────────

    def test_mixed_search_compound_query(self):
        result = classify_v2(
            "khách sạn gần Nhà thờ Đức Bà dưới 1tr2 cho 2 người có wifi"
        )
        self.assertEqual(result.input_kind, "mixed_search")

    def test_mixed_search_amenity_extracted(self):
        result = classify_v2(
            "khách sạn gần Nhà thờ Đức Bà dưới 1tr2 cho 2 người có wifi"
        )
        self.assertIn("wifi", result.amenity_terms)

    def test_mixed_search_confidence(self):
        result = classify_v2(
            "khách sạn gần Nhà thờ Đức Bà dưới 1tr2 cho 2 người có wifi"
        )
        self.assertGreater(result.confidence, 0.80)


class TestClassifierEdgeCases(SimpleTestCase):

    def test_empty_string_returns_unknown(self):
        result = classify_v2("")
        self.assertEqual(result.input_kind, "unknown")

    def test_whitespace_only_returns_unknown(self):
        result = classify_v2("   ")
        self.assertEqual(result.input_kind, "unknown")

    def test_none_coerced_to_string_doesnt_crash(self):
        try:
            result = classify_v2(str(None))
            self.assertIsInstance(result, ClassificationResult)
        except Exception as exc:
            self.fail(f"classify_v2 raised unexpectedly: {exc}")

    def test_greeting_xin_chao(self):
        result = classify_v2("xin chào")
        self.assertEqual(result.input_kind, "greeting")

    def test_greeting_hello(self):
        result = classify_v2("hello")
        self.assertEqual(result.input_kind, "greeting")

    def test_result_is_classification_result(self):
        result = classify_v2("có wifi gần Quận 1")
        self.assertIsInstance(result, ClassificationResult)

    def test_confidence_always_between_0_and_1(self):
        queries = [
            "co wifi", "quan 3", "gan landmark 81",
            "rex hotel", "1 Su Van Hanh, P9, Q5",
            "xin chao", "tim phong o dau cung duoc",
        ]
        for q in queries:
            result = classify_v2(q)
            self.assertGreaterEqual(result.confidence, 0.0, msg=q)
            self.assertLessEqual(result.confidence, 1.0, msg=q)

    def test_amenity_only_no_location_phrase(self):
        result = classify_v2("có hồ bơi")
        self.assertEqual(result.input_kind, "amenity_only")
        self.assertIn("pool", result.amenity_terms)

    def test_multiple_amenities_all_extracted(self):
        result = classify_v2("có wifi có bếp")
        self.assertIn("wifi", result.amenity_terms)
        self.assertIn("kitchen", result.amenity_terms)

    def test_area_variant_phu_nhuan(self):
        result = classify_v2("Phú Nhuận")
        self.assertEqual(result.input_kind, "area")

    def test_near_ben_thanh_landmark(self):
        result = classify_v2("gần chợ Bến Thành")
        self.assertEqual(result.input_kind, "landmark_or_poi")

    def test_context_slots_accepted(self):
        result = classify_v2("co wifi", context_slots={"budget": 500_000})
        self.assertIsInstance(result, ClassificationResult)

    def test_to_dict_returns_required_keys(self):
        result = classify_v2("gần Landmark 81")
        d = result.to_dict()
        for key in ("input_kind", "confidence", "location_phrase", "hotel_name",
                    "area_hint", "amenity_terms", "debug"):
            self.assertIn(key, d)
