"""
Unit tests for InputClassifierV2.

Run:
    cd travel_project/accommodation_project
    python -m pytest chat_api/nlu/test_input_classifier_v2.py -v
    # or without pytest:
    python -m unittest chat_api.nlu.test_input_classifier_v2 -v
"""
from __future__ import annotations

import sys
import os
import unittest

# Make the module importable when run directly from any working directory
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.join(_HERE, "..", "..")  # accommodation_project/
sys.path.insert(0, _APP_ROOT)

from chat_api.nlu.input_classifier_v2 import (
    ClassificationResult,
    classify_v2,
    _detect_amenities,
    _detect_area,
    _detect_poi_category,
    _has_near_cue,
    _is_area_only,
    _remaining_looks_like_hotel_name,
)


# ============================================================================
# Helpers
# ============================================================================

def kind(text: str, **kw) -> str:
    return classify_v2(text, **kw).input_kind


def result(text: str, **kw) -> ClassificationResult:
    return classify_v2(text, **kw)


# ============================================================================
# 1. greeting
# ============================================================================

class TestGreeting(unittest.TestCase):
    def test_xin_chao(self):
        self.assertEqual(kind("xin chào"), "greeting")

    def test_hello(self):
        self.assertEqual(kind("hello"), "greeting")

    def test_hi(self):
        self.assertEqual(kind("hi"), "greeting")

    def test_alo(self):
        self.assertEqual(kind("alo"), "greeting")

    def test_greeting_with_search_not_pure_greeting(self):
        # "xin chào tôi cần tìm khách sạn" — not a pure greeting
        r = result("xin chào tôi cần tìm khách sạn")
        self.assertNotEqual(r.input_kind, "greeting")

    def test_confidence_high(self):
        r = result("xin chào")
        self.assertGreaterEqual(r.confidence, 0.90)


# ============================================================================
# 2. specific_address
# ============================================================================

class TestSpecificAddress(unittest.TestCase):
    def test_full_vn_address(self):
        self.assertEqual(kind("1 Sư Vạn Hạnh, Phường 9, Quận 5, TP HCM"), "specific_address")

    def test_address_with_duong(self):
        self.assertEqual(kind("120 đường Nguyễn Huệ, Quận 1"), "specific_address")

    def test_phuong_quan_pattern(self):
        self.assertEqual(kind("Phường 5, Quận 3"), "specific_address")

    def test_district_alone_is_not_address(self):
        # "Quận 5" alone must NOT be specific_address
        self.assertNotEqual(kind("Quận 5"), "specific_address")

    def test_city_alone_is_not_address(self):
        self.assertNotEqual(kind("TP HCM"), "specific_address")

    def test_location_phrase_populated(self):
        r = result("1 Sư Vạn Hạnh, Phường 9, Quận 5")
        self.assertIsNotNone(r.location_phrase)


# ============================================================================
# 3. mixed_search
# ============================================================================

class TestMixedSearch(unittest.TestCase):
    def test_full_example(self):
        self.assertEqual(
            kind("khách sạn gần Nhà thờ Đức Bà dưới 1tr có wifi"),
            "mixed_search",
        )

    def test_hotel_with_amenity(self):
        # acc_keyword (type) + amenity = mixed
        self.assertEqual(kind("khách sạn có wifi"), "mixed_search")

    def test_hotel_area_amenity(self):
        self.assertEqual(kind("khách sạn quận 3 có hồ bơi"), "mixed_search")

    def test_location_and_budget(self):
        self.assertEqual(kind("gần Bến Thành dưới 500k"), "mixed_search")

    def test_area_and_amenity(self):
        self.assertEqual(kind("ở Phú Nhuận có máy lạnh"), "mixed_search")

    def test_amenity_terms_populated(self):
        r = result("khách sạn có wifi và hồ bơi")
        self.assertIn("wifi", r.amenity_terms)
        self.assertIn("pool", r.amenity_terms)

    def test_area_hint_populated(self):
        r = result("khách sạn quận 3 có wifi")
        self.assertIsNotNone(r.area_hint)


# ============================================================================
# 4. generic_poi_in_area
# ============================================================================

class TestGenericPoiInArea(unittest.TestCase):
    def test_cafe_quan5(self):
        self.assertEqual(kind("gần quán cafe ở Quận 5"), "generic_poi_in_area")

    def test_hospital_phu_nhuan(self):
        self.assertEqual(kind("gần bệnh viện ở Phú Nhuận"), "generic_poi_in_area")

    def test_restaurant_quan1(self):
        self.assertEqual(kind("gần nhà hàng ở Quận 1"), "generic_poi_in_area")

    def test_area_hint_populated(self):
        r = result("gần quán cafe ở Quận 5")
        self.assertIsNotNone(r.area_hint)

    def test_location_phrase_populated(self):
        r = result("gần quán cafe ở Quận 5")
        self.assertIsNotNone(r.location_phrase)

    def test_debug_has_poi_category(self):
        r = result("gần bệnh viện ở Phú Nhuận")
        self.assertIn("poi_category", r.debug)
        self.assertEqual(r.debug["poi_category"], "hospital")


# ============================================================================
# 5. landmark_or_poi
# ============================================================================

class TestLandmarkOrPoi(unittest.TestCase):
    def test_landmark_81(self):
        self.assertEqual(kind("gần Landmark 81"), "landmark_or_poi")

    def test_dinh_doc_lap(self):
        self.assertEqual(kind("gần Dinh Độc Lập"), "landmark_or_poi")

    def test_cho_ben_thanh(self):
        # Chợ Bến Thành is a specific named market, not category+area
        self.assertEqual(kind("gần chợ Bến Thành"), "landmark_or_poi")

    def test_ke_ben(self):
        self.assertEqual(kind("kế bên Bitexco"), "landmark_or_poi")

    def test_xung_quanh(self):
        self.assertEqual(kind("xung quanh nhà thờ Đức Bà"), "landmark_or_poi")

    def test_location_phrase_after_near_cue(self):
        r = result("gần Landmark 81")
        self.assertIsNotNone(r.location_phrase)
        self.assertIn("landmark", r.location_phrase.lower())


# ============================================================================
# 6. amenity_only
# ============================================================================

class TestAmenityOnly(unittest.TestCase):
    def test_parking(self):
        self.assertEqual(kind("có parking"), "amenity_only")

    def test_cho_dau_xe(self):
        self.assertEqual(kind("có chỗ đậu xe"), "amenity_only")

    def test_may_lanh(self):
        self.assertEqual(kind("có máy lạnh"), "amenity_only")

    def test_dieu_hoa(self):
        self.assertEqual(kind("có điều hòa"), "amenity_only")

    def test_wifi_bare(self):
        self.assertEqual(kind("wifi"), "amenity_only")

    def test_ho_boi(self):
        self.assertEqual(kind("có hồ bơi"), "amenity_only")

    def test_may_giat(self):
        self.assertEqual(kind("có máy giặt"), "amenity_only")

    def test_bep(self):
        self.assertEqual(kind("có bếp"), "amenity_only")

    def test_multiple_amenities(self):
        r = result("wifi và hồ bơi")
        self.assertEqual(r.input_kind, "amenity_only")
        self.assertIn("wifi", r.amenity_terms)
        self.assertIn("pool", r.amenity_terms)

    def test_amenity_terms_canonical(self):
        r = result("có parking")
        self.assertIn("parking", r.amenity_terms)

    def test_may_lanh_canonical(self):
        r = result("có máy lạnh")
        self.assertIn("air_conditioner", r.amenity_terms)


# ============================================================================
# 7. hotel_name
# ============================================================================

class TestHotelName(unittest.TestCase):
    def test_rex_hotel(self):
        self.assertEqual(kind("Rex Hotel"), "hotel_name")

    def test_hotel_nikko_saigon(self):
        self.assertEqual(kind("Hotel Nikko Saigon"), "hotel_name")

    def test_khach_san_liberty_central(self):
        self.assertEqual(kind("khách sạn Liberty Central"), "hotel_name")

    def test_original_text_in_hotel_name(self):
        r = result("Rex Hotel")
        self.assertEqual(r.hotel_name, "Rex Hotel")

    def test_hotel_alone_is_not_hotel_name(self):
        # "hotel" alone has no distinctive name remaining
        self.assertNotEqual(kind("hotel"), "hotel_name")

    def test_generic_search_sentence_not_hotel_name(self):
        # "xin chào tôi cần tìm khách sạn" should not be hotel_name
        self.assertNotEqual(kind("xin chào tôi cần tìm khách sạn"), "hotel_name")

    def test_confidence_reasonable(self):
        r = result("khách sạn Liberty Central")
        self.assertGreaterEqual(r.confidence, 0.60)


# ============================================================================
# 8. area
# ============================================================================

class TestArea(unittest.TestCase):
    def test_quan_3(self):
        self.assertEqual(kind("Quận 3"), "area")

    def test_o_phu_nhuan(self):
        self.assertEqual(kind("ở Phú Nhuận"), "area")

    def test_binh_thanh(self):
        self.assertEqual(kind("Bình Thạnh"), "area")

    def test_ha_noi(self):
        self.assertEqual(kind("Hà Nội"), "area")

    def test_da_nang(self):
        self.assertEqual(kind("Đà Nẵng"), "area")

    def test_area_hint_populated(self):
        r = result("Quận 3")
        self.assertIsNotNone(r.area_hint)

    def test_location_phrase_populated(self):
        r = result("Quận 3")
        self.assertIsNotNone(r.location_phrase)

    def test_quan_with_number(self):
        for q in ["Quận 1", "Quận 5", "Quận 12"]:
            with self.subTest(q=q):
                self.assertEqual(kind(q), "area")


# ============================================================================
# 9. unknown
# ============================================================================

class TestUnknown(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(kind(""), "unknown")

    def test_whitespace(self):
        self.assertEqual(kind("   "), "unknown")

    def test_off_topic(self):
        r = result("dự báo thời tiết hôm nay thế nào")
        # No accommodation signals → unknown
        self.assertEqual(r.input_kind, "unknown")

    def test_confidence_low(self):
        r = result("abcdef xyz")
        self.assertLessEqual(r.confidence, 0.50)


# ============================================================================
# Unit tests for private helpers
# ============================================================================

class TestDetectAmenities(unittest.TestCase):
    def test_wifi(self):
        from chat_api.normalizers import normalize_key
        self.assertIn("wifi", _detect_amenities(normalize_key("có wifi")))

    def test_parking(self):
        from chat_api.normalizers import normalize_key
        self.assertIn("parking", _detect_amenities(normalize_key("có chỗ đậu xe")))

    def test_air_conditioner(self):
        from chat_api.normalizers import normalize_key
        self.assertIn("air_conditioner", _detect_amenities(normalize_key("có máy lạnh")))

    def test_no_double_counting(self):
        from chat_api.normalizers import normalize_key
        # "có wifi" should only match once
        result = _detect_amenities(normalize_key("có wifi wifi"))
        self.assertEqual(result.count("wifi"), 1)

    def test_multiple(self):
        from chat_api.normalizers import normalize_key
        result = _detect_amenities(normalize_key("wifi và hồ bơi và máy giặt"))
        self.assertIn("wifi", result)
        self.assertIn("pool", result)
        self.assertIn("washing_machine", result)


class TestDetectArea(unittest.TestCase):
    def test_quan_1(self):
        from chat_api.normalizers import normalize_key
        self.assertIsNotNone(_detect_area(normalize_key("Quận 1")))

    def test_phu_nhuan(self):
        from chat_api.normalizers import normalize_key
        self.assertIsNotNone(_detect_area(normalize_key("Phú Nhuận")))

    def test_empty(self):
        self.assertIsNone(_detect_area(""))

    def test_plain_word_no_area(self):
        from chat_api.normalizers import normalize_key
        self.assertIsNone(_detect_area(normalize_key("đẹp")))


class TestDetectPoiCategory(unittest.TestCase):
    def test_cafe(self):
        from chat_api.normalizers import normalize_key
        self.assertEqual(_detect_poi_category(normalize_key("quán cafe")), "cafe")

    def test_hospital(self):
        from chat_api.normalizers import normalize_key
        self.assertEqual(_detect_poi_category(normalize_key("bệnh viện")), "hospital")

    def test_none_for_plain_text(self):
        self.assertIsNone(_detect_poi_category("nha"))


class TestHasNearCue(unittest.TestCase):
    def test_gan(self):
        from chat_api.normalizers import normalize_key
        self.assertTrue(_has_near_cue(normalize_key("gần Landmark 81")))

    def test_xung_quanh(self):
        from chat_api.normalizers import normalize_key
        self.assertTrue(_has_near_cue(normalize_key("xung quanh chợ")))

    def test_no_cue(self):
        self.assertFalse(_has_near_cue("khach san dep"))


class TestIsAreaOnly(unittest.TestCase):
    def test_quan_3_only(self):
        from chat_api.normalizers import normalize_key
        norm = normalize_key("Quận 3")
        self.assertTrue(_is_area_only(norm, "quan 3"))

    def test_o_phu_nhuan(self):
        from chat_api.normalizers import normalize_key
        norm = normalize_key("ở Phú Nhuận")
        self.assertTrue(_is_area_only(norm, "phu nhuan"))

    def test_hotel_with_area_not_area_only(self):
        from chat_api.normalizers import normalize_key
        norm = normalize_key("khách sạn Quận 3 giá rẻ")
        self.assertFalse(_is_area_only(norm, "quan 3"))


class TestRemainingLooksLikeHotelName(unittest.TestCase):
    def test_proper_name(self):
        self.assertTrue(_remaining_looks_like_hotel_name("liberty central"))

    def test_rex(self):
        self.assertTrue(_remaining_looks_like_hotel_name("rex"))

    def test_generic_words_rejected(self):
        self.assertFalse(_remaining_looks_like_hotel_name("toi can tim"))

    def test_empty_rejected(self):
        self.assertFalse(_remaining_looks_like_hotel_name(""))

    def test_too_short_rejected(self):
        self.assertFalse(_remaining_looks_like_hotel_name("ab"))


# ============================================================================
# Result shape tests
# ============================================================================

class TestResultShape(unittest.TestCase):
    def test_to_dict_keys(self):
        r = classify_v2("có wifi")
        d = r.to_dict()
        self.assertIn("input_kind", d)
        self.assertIn("confidence", d)
        self.assertIn("location_phrase", d)
        self.assertIn("hotel_name", d)
        self.assertIn("area_hint", d)
        self.assertIn("amenity_terms", d)
        self.assertIn("debug", d)

    def test_confidence_in_range(self):
        for text in ["có wifi", "Quận 1", "gần Landmark 81", "xin chào", ""]:
            with self.subTest(text=text):
                r = classify_v2(text)
                self.assertGreaterEqual(r.confidence, 0.0)
                self.assertLessEqual(r.confidence, 1.0)

    def test_debug_has_reason(self):
        r = classify_v2("có wifi")
        self.assertIn("reason", r.debug)


if __name__ == "__main__":
    unittest.main(verbosity=2)
