import json
import os
from unittest.mock import patch

os.environ.setdefault("CHAT_API_ENABLE_HF_AGENT", "0")

from django.test import SimpleTestCase, TestCase

from accommodations.models import Accommodation
from preferences.models import UserPreference

from .agent.llm_parser import _extract_json_object
from .agent.schema_normalizer import extract_budget_bounds, normalize_parsed_result
from .fuzzy_location import resolve_location_fuzzy
from .filter_tree import geocode_anchor
from .location_phrase_cleaner import clean_location_candidate_phrase, has_concrete_place_noun
from .location_gazetteer import generate_location_aliases, load_supported_locations
from .models import PlaceReference
from .normalizers import normalize_key
from .place_geocoder import resolve_place_reference
from .services.geocoder import build_geocode_queries, geocode_place
from .services import parse_user_text
from .text_normalizer import normalize_user_text
from .geocoder.validator import validate_geocode_candidate
from recommendations.services import get_candidate_accommodations


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
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Landmark 81")
        self.assertEqual(result["anchor_kind"], "landmark")
        self.assertIsNone(result["canonical_area"])

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

        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Chợ Rẫy")
        self.assertEqual(result["anchor_kind"], "landmark")
        self.assertIsNone(result["canonical_area"])
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

    def test_location_phrase_cleaner_removes_request_words_without_place_hardcode(self):
        keep_cue = clean_location_candidate_phrase(
            "tôi muốn thuê gần Bưu điện Trung tâm Thành phố giúp tôi",
            strip_leading_cues=False,
        )
        place_only = clean_location_candidate_phrase("gần Bưu điện Trung tâm Thành phố giúp tôi")

        self.assertEqual(keep_cue, "gần Bưu điện Trung tâm Thành phố")
        self.assertEqual(place_only, "Bưu điện Trung tâm Thành phố")
        self.assertTrue(has_concrete_place_noun(place_only))

    def test_location_phrase_cleaner_normalizes_building_typo(self):
        self.assertEqual(clean_location_candidate_phrase("Gần toàn Landmark"), "tòa Landmark")
        self.assertTrue(has_concrete_place_noun("tòa Landmark"))

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

    def test_osm_geocoder_dedupes_same_place_before_ambiguity(self):
        row = {
            "place_id": 257160068,
            "osm_type": "way",
            "osm_id": 1223373335,
            "lat": "10.8395793",
            "lon": "106.8421165",
            "class": "landuse",
            "type": "residential",
            "name": "Vinhomes Grand Park",
            "display_name": "Vinhomes Grand Park, Phường Long Bình, Thành phố Thủ Đức, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "residential": "Vinhomes Grand Park",
                "suburb": "Phường Long Bình",
                "city": "Thành phố Thủ Đức",
                "country": "Việt Nam",
                "country_code": "vn",
            },
        }
        duplicate = {**row, "place_id": 259089224}
        bus_stop = {
            **row,
            "place_id": 257149808,
            "osm_type": "node",
            "osm_id": 11868700590,
            "type": "bus_stop",
            "class": "highway",
            "lat": "10.8456143",
            "lon": "106.8429272",
            "address": {**row["address"], "highway": "Vinhomes Grand Park"},
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[row, duplicate, bus_stop],
        ):
            result = geocode_place("Vinhomes Grand Park", city_hint="Hồ Chí Minh, Việt Nam")

        self.assertTrue(result.success)
        self.assertEqual(result.canonical_name, "Vinhomes Grand Park")
        self.assertAlmostEqual(result.latitude, 10.8395793)
        self.assertAlmostEqual(result.longitude, 106.8421165)

    def test_osm_geocoder_accepts_named_map_anchor_proxy(self):
        row = {
            "place_id": 258600693,
            "osm_type": "node",
            "osm_id": 6047997502,
            "lat": "10.7706801",
            "lon": "106.7048640",
            "class": "highway",
            "type": "bus_stop",
            "name": "Tòa nhà Bitexco",
            "display_name": "Tòa nhà Bitexco, Hàm Nghi, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "highway": "Tòa nhà Bitexco",
                "road": "Hàm Nghi",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[row],
        ):
            result = geocode_place("tòa Bitexco", city_hint="Hồ Chí Minh, Việt Nam")

        self.assertTrue(result.success)
        self.assertEqual(result.canonical_name, "Tòa nhà Bitexco")
        self.assertEqual(result.place_type, "bus_stop")
        self.assertGreaterEqual(result.confidence, 0.70)

    def test_osm_geocoder_collapses_same_map_place_before_ambiguity(self):
        theme_park = {
            "place_id": 258710900,
            "osm_type": "way",
            "osm_id": 32735046,
            "lat": "10.7643251",
            "lon": "106.6387195",
            "class": "tourism",
            "type": "theme_park",
            "name": "Công viên Văn hóa Đầm Sen",
            "display_name": "Công viên Văn hóa Đầm Sen, Hòa Bình, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "tourism": "Công viên Văn hóa Đầm Sen",
                "road": "Hòa Bình",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.33,
        }
        park = {
            "place_id": 268782244,
            "osm_type": "way",
            "osm_id": 1168427916,
            "lat": "10.7659103",
            "lon": "106.6386430",
            "class": "leisure",
            "type": "park",
            "name": "Công Viên Văn hóa Đầm Sen",
            "display_name": "Công Viên Văn hóa Đầm Sen, Phường Bình Thới, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "park": "Công Viên Văn hóa Đầm Sen",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.08,
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[theme_park, park],
        ):
            result = geocode_place("Đầm Sen", city_hint="Hồ Chí Minh, Việt Nam")

        self.assertTrue(result.success)
        self.assertEqual(result.canonical_name, "Công viên Văn hóa Đầm Sen")
        self.assertEqual(result.place_type, "theme_park")
        self.assertNotEqual(result.unresolved_reason, "ambiguous_geocoder_match")

    def test_osm_geocoder_collapses_transit_prefix_for_same_map_place(self):
        theatre = {
            "place_id": 258719612,
            "osm_type": "way",
            "osm_id": 801710792,
            "lat": "10.7767437",
            "lon": "106.7032488",
            "class": "amenity",
            "type": "theatre",
            "name": "Nhà hát Thành phố",
            "display_name": "Nhà hát Thành phố, Công trường Lam Sơn, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "amenity": "Nhà hát Thành phố",
                "road": "Công trường Lam Sơn",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.39,
        }
        station = {
            "place_id": 260453251,
            "osm_type": "way",
            "osm_id": 1162989826,
            "lat": "10.7752950",
            "lon": "106.7018388",
            "class": "railway",
            "type": "station",
            "name": "Ga Nhà Hát Thành Phố",
            "display_name": "Ga Nhà Hát Thành Phố, Lê Lợi, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "railway": "Ga Nhà Hát Thành Phố",
                "road": "Lê Lợi",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.0001,
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[theatre, station],
        ):
            result = geocode_place("nhà hát thành phố", city_hint="Hồ Chí Minh, Việt Nam")

        self.assertTrue(result.success)
        self.assertEqual(result.canonical_name, "Nhà hát Thành phố")
        self.assertEqual(result.place_type, "theatre")
        self.assertNotEqual(result.unresolved_reason, "ambiguous_geocoder_match")

    def test_osm_geocoder_returns_map_candidates_for_far_clusters(self):
        first = {
            "place_id": 3001,
            "osm_type": "way",
            "osm_id": 9001,
            "lat": "10.7767437",
            "lon": "106.7032488",
            "class": "amenity",
            "type": "theatre",
            "name": "Nhà hát Hòa Bình",
            "display_name": "Nhà hát Hòa Bình, Công trường Lam Sơn, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "amenity": "Nhà hát Hòa Bình",
                "road": "Công trường Lam Sơn",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.3,
        }
        second = {
            "place_id": 3002,
            "osm_type": "way",
            "osm_id": 9002,
            "lat": "10.8350000",
            "lon": "106.6600000",
            "class": "amenity",
            "type": "theatre",
            "name": "Nhà hát Hòa Bình",
            "display_name": "Nhà hát Hòa Bình, Đường Số 1, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "amenity": "Nhà hát Hòa Bình",
                "road": "Đường Số 1",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.3,
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[first, second],
        ):
            result = geocode_place("Nhà hát Hòa Bình", city_hint="Hồ Chí Minh, Việt Nam")

        self.assertFalse(result.success)
        self.assertEqual(result.unresolved_reason, "ambiguous_geocoder_match")
        self.assertEqual(len(result.location_candidates), 2)
        visible_candidate = result.location_candidates[0]
        self.assertIn("name", visible_candidate)
        self.assertIn("address", visible_candidate)
        self.assertNotIn("lat", visible_candidate)
        self.assertNotIn("lon", visible_candidate)
        self.assertIn("lat", visible_candidate["payload"]["selected_place"])


class ConveniencePipelineTests(SimpleTestCase):
    @staticmethod
    def _geocoded_place(name: str, **overrides):
        data = {
            "name": name,
            "lat": 10.7770,
            "lon": 106.6954,
            "display_name": f"{name}, Thành phố Hồ Chí Minh",
            "kind": "attraction",
            "default_radius_km": 3.0,
            "source": "osm",
            "provider": "osm",
            "confidence": 0.9,
            "address": {"city": "Thành phố Hồ Chí Minh"},
        }
        data.update(overrides)
        return data

    def test_thu_duc_compact_recommends_partially_without_user_action(self):
        result = parse_user_text("tôi muốn ở gần thuduc")

        self.assertEqual(result["canonical_area"], "Thủ Đức")
        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["recommendation_level"], "partial")
        self.assertTrue(result["can_show_recommendations"])
        self.assertFalse(result["needs_user_action"])
        self.assertIn("gần Thủ Đức", result["polite_bot_message"])

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
        self.assertIn("địa điểm", result["polite_bot_message"])

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
        self.assertEqual(result["location_mode"], "anywhere")
        self.assertTrue(result["explicit_anywhere"])
        self.assertFalse(result["can_show_recommendations"])
        self.assertIn("ngân sách", result["follow_up_question"])

    def test_soft_filter_anywhere_budget_people_does_not_guess_district(self):
        result = parse_user_text("ở đâu cũng được dưới 1 triệu cho 2 người")

        self.assertTrue(result["success"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "anywhere")
        self.assertTrue(result["explicit_anywhere"])
        self.assertIsNone(result["canonical_area"])
        self.assertIsNone(result["slots"]["area"])
        self.assertEqual(result["slots"]["budget_max"], 1_000_000)
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertIn("budget_max", result["available_slots"])
        self.assertIn("guest_count", result["available_slots"])

    def test_soft_filter_only_budget_can_recommend(self):
        result = parse_user_text("dưới 1 triệu")

        self.assertTrue(result["success"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertTrue(result["partial_intent"])
        self.assertEqual(result["slots"]["budget_max"], 1_000_000)
        self.assertEqual(result["filter_tree"]["filters"][0]["key"], "budget_max")
        self.assertIn("location", result["missing_filter_slots"])
        self.assertIn("guest_count", result["missing_filter_slots"])
        self.assertIn("khu vực hoặc địa danh", result["follow_up_question"])

    def test_soft_filter_only_guest_count_does_not_guess_district(self):
        result = parse_user_text("cho 2 người")

        self.assertTrue(result["success"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertNotEqual(result.get("canonical_area"), "Quận 2")
        self.assertIsNone(result["slots"]["area"])
        self.assertEqual(result["location_mode"], "unknown")
        self.assertIn("guest_count", result["available_slots"])

    def test_soft_filter_only_amenity_can_recommend(self):
        result = parse_user_text("có hồ bơi")

        self.assertTrue(result["success"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertIn("pool", result["slots"]["required_amenities"])
        amenity_nodes = [node for node in result["filter_tree"]["filters"] if node["key"] == "amenities"]
        self.assertEqual(amenity_nodes[0]["value"], ["pool"])

    def test_required_soft_filters_do_not_call_geocoder(self):
        geocode_anchor.cache_clear()
        cases = [
            ("Tôi muốn thuê căn hộ", "accommodation_types", "apartment"),
            ("căn hộ", "accommodation_types", "apartment"),
            ("Khách sạn", "accommodation_types", "hotel"),
            ("có parking", "required_amenities", "parking"),
            ("có chỗ đậu xe", "required_amenities", "parking"),
        ]
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            for text, key, expected in cases:
                with self.subTest(text=text):
                    result = parse_user_text(text, include_debug=True)
                    self.assertTrue(result["can_show_recommendations"])
                    self.assertEqual(result["recommendation_level"], "partial")
                    self.assertIn(expected, result["slots"][key])
                    self.assertFalse(result["geocoder_called"])
                    self.assertFalse(result["unresolved_location"])
                    self.assertEqual(result["missing_slots"], ["location"])
        mock_resolve.assert_not_called()

    def test_protected_accommodation_type_is_not_resolved_as_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("tôi muốn tìm chỗ ở căn hộ", include_debug=True)

        self.assertIn("apartment", result["slots"]["accommodation_types"])
        self.assertIn(result["location_mode"], {"unknown", None})
        self.assertIsNone(result["slots"]["area"])
        self.assertNotEqual(result.get("canonical_area"), "Cần Thơ")
        self.assertFalse(result["geocoder_called"])
        mock_resolve.assert_not_called()
        protected = result["debug_metadata"]["protected_spans"]
        self.assertIn({"text": "căn hộ", "type": "accommodation_type", "value": "apartment"}, protected)

    def test_homestay_typos_are_type_not_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            homtay = parse_user_text("Tôi muốn tìm hómtay", include_debug=True)
            homstay = parse_user_text("Tôi muốn tìn nhà ở Homstay", include_debug=True)

        self.assertIn("homestay", homtay["slots"]["accommodation_types"])
        self.assertFalse(homtay["geocoder_called"])
        self.assertIn("homestay", homstay["slots"]["accommodation_types"])
        self.assertNotEqual(homstay.get("canonical_area"), "Nhà Bè")
        self.assertIsNone(homstay["slots"]["area"])
        self.assertFalse(homstay["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_single_generic_nha_is_not_nha_be_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("Nhà", include_debug=True)

        self.assertNotEqual(result.get("canonical_area"), "Nhà Bè")
        self.assertIsNone(result["slots"]["area"])
        self.assertEqual(result["location_mode"], "unknown")
        self.assertFalse(result["geocoder_called"])
        self.assertEqual(result["follow_up_question"], "Bạn muốn tìm loại chỗ ở nào hoặc khu vực nào rõ hơn không?")
        mock_resolve.assert_not_called()

    def test_parking_and_kitchen_amenities_do_not_geocode(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            parking = parse_user_text("parking", include_debug=True)
            co_parking = parse_user_text("có parking", include_debug=True)
            kitchen = parse_user_text("có bếp", include_debug=True)

        self.assertIn("parking", parking["slots"]["required_amenities"])
        self.assertFalse(parking["geocoder_called"])
        self.assertIn("parking", co_parking["slots"]["required_amenities"])
        self.assertFalse(co_parking["geocoder_called"])
        self.assertIn("kitchen", kitchen["slots"]["required_amenities"])
        self.assertFalse(kitchen["geocoder_called"])
        self.assertNotIn("Bếp Nhà", str(kitchen.get("location_display_label") or ""))
        mock_resolve.assert_not_called()

    def test_required_parking_typo_is_amenity_not_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("có đậu xxe", include_debug=True)

        self.assertIn("parking", result["slots"]["required_amenities"])
        self.assertNotEqual(result.get("location_phrase"), "có đậu xxe")
        self.assertIsNone(result["slots"]["area"])
        self.assertFalse(result["geocoder_called"])
        self.assertFalse(result["unresolved_location"])
        mock_resolve.assert_not_called()

    def test_required_air_conditioner_alias_is_not_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("có máy lạnh", include_debug=True)

        self.assertIn("air_conditioner", result["slots"]["required_amenities"])
        self.assertIsNone(result.get("location_phrase"))
        self.assertFalse(result["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_required_parking_follow_up_reuses_context_without_geocoder(self):
        first = parse_user_text("khách sạn ở Hà Nội", include_debug=True)
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            follow_up = parse_user_text("parking", context_slots=first["slots"], include_debug=True)

        self.assertIn("parking", follow_up["slots"]["required_amenities"])
        self.assertEqual(follow_up["location_mode"], "area")
        self.assertEqual(follow_up["slots"]["area"], "Hà Nội")
        self.assertFalse(follow_up["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_amenity_plus_clear_area_keeps_only_area_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("có bếp gần Nhà Bè", include_debug=True)

        self.assertIn("kitchen", result["slots"]["required_amenities"])
        self.assertEqual(result["canonical_area"], "Nhà Bè")
        self.assertEqual(result["location_mode"], "area")
        self.assertTrue(result["area_match"])
        self.assertFalse(result["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_type_plus_strong_place_phrase_uses_near_anchor(self):
        result = parse_user_text("căn hộ gần sân bay tân sơn nhất", include_debug=True)

        self.assertIn("apartment", result["slots"]["accommodation_types"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_phrase"], "sân bay tân sơn nhất")
        self.assertEqual(result["anchor_name"], "Tân Sơn Nhất")
        self.assertFalse(result["geocoder_called"])

    def test_generic_airport_needs_clarification_without_geocoder(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("gần sân bay", include_debug=True)

        self.assertTrue(result["ambiguous_location"])
        self.assertFalse(result["can_show_recommendations"])
        self.assertFalse(result["geocoder_called"])
        self.assertIsNone(result["anchor_lat"])
        self.assertIn("sân bay nào", result["follow_up_question"])
        mock_resolve.assert_not_called()

    def test_lang_dai_hoc_does_not_autopick_cafe(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("Làng đại học", include_debug=True)

        self.assertTrue(result["ambiguous_location"])
        self.assertFalse(result["geocoder_called"])
        self.assertNotEqual(result.get("anchor_kind"), "cafe")
        mock_resolve.assert_not_called()

    def test_city_center_typo_is_semantic_location_not_poi(self):
        geocode_anchor.cache_clear()
        text = "Tôi muốn đi chơi ở truang tâm thành phố cậu kiếm nhà hay khách sạn ở đâu gần đó nhé tầm 2 người chi phí dưới 5 triệu"
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text(text, include_debug=True)

        self.assertIn("trung tâm thành phố", result["debug_metadata"]["normalized_text"])
        self.assertEqual(result["location_mode"], "city_center")
        self.assertEqual(result["location_phrase"], "trung tâm thành phố")
        self.assertEqual(result["anchor_kind"], "city_center")
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertEqual(result["slots"]["budget_max"], 5_000_000)
        self.assertIn("hotel", result["slots"]["accommodation_types"])
        self.assertNotIn("nhẹ cafe", str(result.get("location_display_label") or "").lower())
        self.assertNotEqual(result.get("canonical_area"), "Nhà Bè")
        self.assertFalse(result["geocoder_called"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["search_origin"]["type"], "semantic_center")
        self.assertEqual(result["location_meta"]["origin_type"], "semantic_center")
        mock_resolve.assert_not_called()

    def test_city_center_short_phrases_do_not_geocode_raw_center(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            center = parse_user_text("trung tâm thành phố", include_debug=True)
            near_center = parse_user_text("gần trung tâm", include_debug=True)

        self.assertEqual(center["location_mode"], "city_center")
        self.assertFalse(center["geocoder_called"])
        self.assertEqual(center["debug_metadata"]["geocoder_block_reason"], "abstract_city_center_location")
        self.assertEqual(near_center["location_mode"], "city_center")
        self.assertFalse(near_center["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_concrete_poi_with_center_words_uses_geocoder_not_city_center(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value=self._geocoded_place(
                "Bưu điện Trung tâm Sài Gòn",
                kind="post_office",
                lat=10.7799557,
                lon=106.6999921,
            ),
        ) as mock_resolve:
            result = parse_user_text("gần bưu điện trung tâm thành phố", include_debug=True)

        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_phrase"], "bưu điện trung tâm thành phố")
        self.assertEqual(result["anchor_name"], "Bưu điện Trung tâm Sài Gòn")
        self.assertTrue(result["geocoder_called"])
        self.assertNotEqual(result.get("anchor_kind"), "city_center")
        mock_resolve.assert_called()

    def test_house_or_hotel_is_lodging_not_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("nhà hay khách sạn", include_debug=True)

        self.assertIn("hotel", result["slots"]["accommodation_types"])
        self.assertNotEqual(result.get("canonical_area"), "Nhà Bè")
        self.assertIn(result["location_mode"], {"unknown", None})
        self.assertFalse(result["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_city_center_rejects_cafe_geocoder_candidate(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "nhẹ cafe - Đền Đô",
                "lat": 21.1,
                "lon": 105.9,
                "display_name": "nhẹ cafe - Đền Đô",
                "kind": "cafe",
                "confidence": 0.9,
                "provider": "osm",
            },
        ) as mock_resolve:
            result = parse_user_text("trung tâm thành phố", include_debug=True)

        self.assertEqual(result["location_mode"], "city_center")
        self.assertNotEqual(result.get("anchor_name"), "nhẹ cafe - Đền Đô")
        self.assertFalse(result["geocoder_called"])
        self.assertEqual(result["rejected_geocoder_results"], [])
        mock_resolve.assert_not_called()

    def test_soft_filter_area_mode_keeps_budget_and_people(self):
        result = parse_user_text("ở quận 3 dưới 1 triệu cho 2 người")

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "area")
        self.assertEqual(result["location_phrase"], "Quận 3")
        self.assertEqual(result["canonical_area"], "Quận 3")
        self.assertEqual(result["slots"]["budget_max"], 1_000_000)
        self.assertEqual(result["slots"]["guest_count"], 2)

    def test_soft_filter_near_district_uses_anchor(self):
        result = parse_user_text("gần Thủ Đức dưới 1 triệu")

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Thủ Đức")
        self.assertEqual(result["anchor_kind"], "district")
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertGreater(result["anchor_radius_km"], 0)

    def test_soft_filter_near_landmark_does_not_collapse_to_city(self):
        result = parse_user_text("gần nhà thờ Đức Bà")

        self.assertTrue(result["success"])
        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_kind"], "landmark")
        self.assertEqual(result["anchor_name"], "Nhà thờ Đức Bà")
        self.assertIsNone(result["canonical_area"])
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])

    def test_soft_filter_near_bitexco_uses_map_api_result(self):
        geocode_anchor.cache_clear()
        row = {
            "place_id": 258600693,
            "osm_type": "node",
            "osm_id": 6047997502,
            "lat": "10.7706801",
            "lon": "106.7048640",
            "class": "highway",
            "type": "bus_stop",
            "name": "Tòa nhà Bitexco",
            "display_name": "Tòa nhà Bitexco, Hàm Nghi, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "highway": "Tòa nhà Bitexco",
                "road": "Hàm Nghi",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[row],
        ) as mock_fetch_osm:
            result = parse_user_text("khách sạn gần tòa Bitexco", include_debug=True)

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_source"], "osm")
        self.assertEqual(result["anchor_name"], "Tòa nhà Bitexco")
        self.assertEqual(result["anchor_kind"], "bus_stop")
        self.assertTrue(result["geocoder_called"])
        self.assertFalse(result["unresolved_location"])
        self.assertIsNone(result["canonical_area"])
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertIn("Bitexco", result["location_display_label"])
        mock_fetch_osm.assert_called()
        geocode_anchor.cache_clear()

    def test_soft_filter_far_map_clusters_asks_user_to_choose_candidate(self):
        geocode_anchor.cache_clear()
        first = {
            "place_id": 3001,
            "osm_type": "way",
            "osm_id": 9001,
            "lat": "10.7767437",
            "lon": "106.7032488",
            "class": "amenity",
            "type": "theatre",
            "name": "Nhà hát Hòa Bình",
            "display_name": "Nhà hát Hòa Bình, Công trường Lam Sơn, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "amenity": "Nhà hát Hòa Bình",
                "road": "Công trường Lam Sơn",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.3,
        }
        second = {
            **first,
            "place_id": 3002,
            "osm_id": 9002,
            "lat": "10.8350000",
            "lon": "106.6600000",
            "display_name": "Nhà hát Hòa Bình, Đường Số 1, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "amenity": "Nhà hát Hòa Bình",
                "road": "Đường Số 1",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[first, second],
        ):
            result = parse_user_text("khách sạn gần Nhà hát Hòa Bình", include_debug=True)

        self.assertEqual(result["location_status"], "multiple_choice")
        self.assertEqual(result["location_mode"], "multiple_choice")
        self.assertTrue(result["ambiguous_location"])
        self.assertEqual(len(result["location_candidates"]), 2)
        self.assertFalse(result["can_show_recommendations"])
        self.assertIn("payload", result["location_candidates"][0])
        geocode_anchor.cache_clear()

    def test_selected_map_candidate_context_changes_to_new_place(self):
        selected_place = {
            "name": "Bưu Điện Việt Nam",
            "display_name": "Bưu Điện Việt Nam, 447 Trần Hưng Đạo, Thành phố Hồ Chí Minh",
            "kind": "post_office",
            "lat": 10.7581,
            "lon": 106.6899,
            "default_radius_km": 2.5,
            "source": "osm",
            "provider": "osm",
            "address": {"road": "Trần Hưng Đạo", "city": "Thành phố Hồ Chí Minh"},
        }
        context = {
            "preferred_type": "hotel",
            "accommodation_types": ["hotel"],
            "location_mode": "near_anchor",
            "location_phrase": "Bưu Điện Việt Nam",
            "selected_place": selected_place,
        }

        result = parse_user_text("Gần Nhà thờ Đức Bà", context_slots=context)

        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Nhà thờ Đức Bà")
        self.assertNotEqual(result["anchor_name"], "Bưu Điện Việt Nam")
        self.assertNotIn("selected_place", result["slots"])
        self.assertNotIn("selected_place", {item["key"] for item in result.get("confirm_table", [])})

    def test_selected_map_candidate_context_stays_for_non_location_follow_up(self):
        selected_place = {
            "name": "Bưu Điện Việt Nam",
            "display_name": "Bưu Điện Việt Nam, 447 Trần Hưng Đạo, Thành phố Hồ Chí Minh",
            "kind": "post_office",
            "lat": 10.7581,
            "lon": 106.6899,
            "default_radius_km": 2.5,
            "source": "osm",
            "provider": "osm",
            "address": {"road": "Trần Hưng Đạo", "city": "Thành phố Hồ Chí Minh"},
        }
        context = {
            "preferred_type": "hotel",
            "accommodation_types": ["hotel"],
            "location_mode": "near_anchor",
            "location_phrase": "Bưu Điện Việt Nam",
            "selected_place": selected_place,
        }

        result = parse_user_text("2 người", context_slots=context)

        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Bưu Điện Việt Nam")
        self.assertEqual(result["slots"]["guest_count"], 2)
        self.assertNotIn("selected_place", {item["key"] for item in result.get("confirm_table", [])})

    def test_soft_filter_landmark_building_typo_uses_map_api_result(self):
        geocode_anchor.cache_clear()
        row = {
            "place_id": 4101,
            "osm_type": "way",
            "osm_id": 8101,
            "lat": "10.7948877",
            "lon": "106.7216825",
            "class": "highway",
            "type": "bus_stop",
            "name": "Tòa nhà Landmark 81",
            "display_name": "Tòa nhà Landmark 81, Bình Thạnh, Thành phố Hồ Chí Minh, Việt Nam",
            "address": {
                "highway": "Tòa nhà Landmark 81",
                "suburb": "Bình Thạnh",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
            "importance": 0.4,
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._fetch_osm",
            return_value=[row],
        ):
            result = parse_user_text("Gần toàn Landmark", include_debug=True)

        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Tòa nhà Landmark 81")
        self.assertTrue(result["geocoder_called"])
        geocode_anchor.cache_clear()

    def test_soft_filter_near_suoi_tien_uses_local_reference(self):
        result = parse_user_text("gần Suối Tiên")

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Suối Tiên")
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertIn("Suối Tiên", result["polite_bot_message"])
        self.assertEqual(result["confirm_table"][0]["label"], "Khu vực")
        self.assertEqual(result["confirm_table"][0]["display_value"], "gần Suối Tiên")

    def test_near_hcm_history_museum_accepts_high_similarity_osm_result(self):
        geocode_anchor.cache_clear()
        row = {
            "place_id": 258617149,
            "osm_type": "relation",
            "osm_id": 17758150,
            "lat": "10.7879719",
            "lon": "106.7049563",
            "class": "tourism",
            "type": "museum",
            "importance": 0.3754795826599041,
            "name": "Bảo tàng Lịch sử Thành phố Hồ Chí Minh",
            "display_name": (
                "Bảo tàng Lịch sử Thành phố Hồ Chí Minh, 2, Nguyễn Thị Minh Khai, "
                "Thành phố Hồ Chí Minh, Việt Nam"
            ),
            "address": {
                "tourism": "Bảo tàng Lịch sử Thành phố Hồ Chí Minh",
                "house_number": "2",
                "road": "Nguyễn Thị Minh Khai",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
        }

        with patch.dict(os.environ, {"GEOCODER_CACHE_ENABLED": "false"}), patch(
            "chat_api.services.geocoder._provider_searches",
            return_value=[],
        ), patch("chat_api.services.geocoder._fetch_osm", return_value=[row]):
            result = parse_user_text("Gần bảo tàng lịch sử thành phố giá 2 đến 5 triệu", include_debug=True)

        self.assertEqual(result["location_status"], "ok")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Bảo tàng Lịch sử Thành phố Hồ Chí Minh")
        self.assertEqual(result["anchor_kind"], "museum")
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertFalse(result["unresolved_location"])
        self.assertEqual(result["slots"]["budget_min"], 2_000_000)
        self.assertEqual(result["slots"]["budget_max"], 5_000_000)
        geocode_anchor.cache_clear()

    def test_soft_filter_unknown_landmark_uses_osm_geocoder(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Phố đi bộ Nguyễn Huệ",
                "lat": 10.7731,
                "lon": 106.7031,
                "display_name": "Phố đi bộ Nguyễn Huệ, Quận 1, Thành phố Hồ Chí Minh",
                "kind": "pedestrian",
                "default_radius_km": 5.0,
                "source": "osm_geocoder",
                "provider": "osm",
                "confidence": 0.88,
                "map_area": "Quận 1",
                "address": {"city_district": "Quận 1"},
                "query": "pho di bo nguyen hue, Hồ Chí Minh, Việt Nam",
                "geocoder_queries": ["Phố đi bộ Nguyễn Huệ, Việt Nam"],
            },
        ) as mock_resolve:
            result = parse_user_text("gần Phố đi bộ Nguyễn Huệ")

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_source"], "osm_geocoder")
        self.assertEqual(result["anchor_name"], "Phố đi bộ Nguyễn Huệ")
        self.assertEqual(result["location_phrase"], "Phố đi bộ Nguyễn Huệ")
        self.assertEqual(result["provider"], "osm")
        self.assertEqual(result["resolved_place"]["canonical_name"], "Phố đi bộ Nguyễn Huệ")
        self.assertEqual(result["map_area"], "Quận 1")
        self.assertIsNone(result["canonical_area"])
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertNotIn("theo bản đồ", result["confirm_table"][0]["display_value"])
        mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_required_standalone_pois_resolve_as_near_anchor(self):
        geocode_anchor.cache_clear()
        cases = [
            ("Đầm Sen", "Đầm Sen"),
            ("Công viên Văn hóa Đầm Sen", "Công viên Văn hóa Đầm Sen"),
            ("Snow Town Sài Gòn", "Snow Town Sài Gòn"),
            ("Bình Quới 1", "Bình Quới 1"),
        ]
        for text, name in cases:
            with self.subTest(text=text):
                geocode_anchor.cache_clear()
                with patch(
                    "chat_api.filter_tree.resolve_place_reference",
                    return_value={
                        "name": name,
                        "lat": 10.77,
                        "lon": 106.69,
                        "display_name": f"{name}, Thành phố Hồ Chí Minh",
                        "kind": "attraction",
                        "default_radius_km": 2.5,
                        "source": "osm",
                        "provider": "osm",
                        "confidence": 0.9,
                        "address": {"city": "Thành phố Hồ Chí Minh"},
                    },
                ) as mock_resolve:
                    result = parse_user_text(text)
                self.assertEqual(result["location_mode"], "near_anchor")
                self.assertEqual(result["anchor_name"], name)
                self.assertTrue(result["geocoder_called"])
                self.assertNotIn("hotel", result["slots"]["accommodation_types"])
                mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_required_poi_noun_does_not_collapse_to_area(self):
        geocode_anchor.cache_clear()
        for text in ("Gần chợ Tân Bình", "Chợ Tân Bình"):
            with self.subTest(text=text):
                geocode_anchor.cache_clear()
                with patch(
                    "chat_api.filter_tree.resolve_place_reference",
                    return_value=self._geocoded_place(
                        "Chợ Tân Bình",
                        lat=10.7867,
                        lon=106.6524,
                        kind="marketplace",
                        map_area="Tân Bình",
                        address={"city_district": "Tân Bình", "city": "Thành phố Hồ Chí Minh"},
                    ),
                ) as mock_resolve:
                    result = parse_user_text(text, include_debug=True)

                self.assertEqual(result["location_mode"], "near_anchor")
                self.assertIn("Chợ Tân Bình", result["anchor_name"])
                self.assertIsNone(result["canonical_area"])
                self.assertNotEqual(result["location_mode"], "area")
                mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_required_near_bui_vien_uses_geocoder_or_cache(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value=self._geocoded_place(
                "Bùi Viện",
                lat=10.7678,
                lon=106.6931,
                kind="pedestrian",
                provider="osm_nominatim",
                source="osm_nominatim",
            ),
        ) as mock_resolve:
            result = parse_user_text("Gần Bùi Viện", include_debug=True)

        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Bùi Viện")
        self.assertTrue(result["geocoder_called"])
        self.assertEqual(result["location_source"], "osm_nominatim")
        mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_required_new_location_candidate_does_not_fallback_to_context(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value=self._geocoded_place("Bến Nhà Rồng", lat=10.7680, lon=106.7060),
        ):
            first = parse_user_text("Bến Nhà Rồng", include_debug=True)

        with patch("chat_api.filter_tree.resolve_place_reference", return_value=None):
            follow_up = parse_user_text("Thảo Cầm Viên", context_slots=first["slots"], include_debug=True)

        self.assertEqual(first["location_mode"], "near_anchor")
        self.assertEqual(follow_up["location_mode"], "near_anchor")
        self.assertTrue(follow_up["unresolved_location"])
        self.assertEqual(normalize_key(follow_up["location_phrase"]), "thao cam vien")
        self.assertNotEqual(follow_up.get("anchor_name"), "Bến Nhà Rồng")
        self.assertNotIn("Bến Nhà Rồng", str(follow_up.get("location_display_label") or ""))
        geocode_anchor.cache_clear()

    def test_required_radius_parses_near_anchor_with_amenity(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value=self._geocoded_place(
                "Bùi Viện",
                lat=10.7678,
                lon=106.6931,
                kind="pedestrian",
            ),
        ) as mock_resolve:
            result = parse_user_text("gần Bùi Viện trong 2km có parking", include_debug=True)

        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(normalize_key(result["location_phrase"]), "bui vien")
        self.assertEqual(result["search_radius_km"], 2.0)
        self.assertEqual(result["anchor_radius_km"], 2.0)
        self.assertEqual(result["search_origin"]["radius_km"], 2.0)
        self.assertIn("parking", result["slots"]["required_amenities"])
        self.assertIn("2km", result["location_display_label"])
        mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_required_near_dinh_doc_lap_does_not_use_wrong_map_area(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Dinh Độc Lập",
                "lat": 10.7770,
                "lon": 106.6954,
                "display_name": "Dinh Độc Lập, Quận 1, Thành phố Hồ Chí Minh",
                "kind": "attraction",
                "default_radius_km": 2.5,
                "source": "osm",
                "provider": "osm",
                "confidence": 0.9,
                "map_area": "Quận 1",
                "address": {"city_district": "Quận 1", "city": "Thành phố Hồ Chí Minh"},
            },
        ):
            result = parse_user_text("gần Dinh Độc Lập")

        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertIn(result["anchor_name"], {"Dinh Độc Lập", "Reunification Palace", "Independence Palace"})
        self.assertNotEqual(result.get("map_area"), "Thủ Đức")
        self.assertNotIn("Thủ Đức", result.get("polite_bot_message", ""))
        geocode_anchor.cache_clear()

    def test_required_mixed_poi_type_and_amenity(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Đầm Sen",
                "lat": 10.763,
                "lon": 106.635,
                "display_name": "Đầm Sen, Thành phố Hồ Chí Minh",
                "kind": "attraction",
                "default_radius_km": 2.5,
                "source": "osm",
                "provider": "osm",
                "confidence": 0.9,
                "address": {"city": "Thành phố Hồ Chí Minh"},
            },
        ):
            result = parse_user_text("tôi muốn tìm khách sạn gần Đầm Sen có parking")

        self.assertIn("hotel", result["slots"]["accommodation_types"])
        self.assertIn("parking", result["slots"]["required_amenities"])
        self.assertEqual(normalize_key(result["location_phrase"]), "dam sen")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["anchor_name"], "Đầm Sen")
        geocode_anchor.cache_clear()

    def test_required_unknown_poi_does_not_invent_location(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference", return_value=None):
            no_filter = parse_user_text("gần abcxyz lạ quá")
            with_filter = parse_user_text("khách sạn gần abcxyz lạ quá")

        self.assertTrue(no_filter["unresolved_location"])
        self.assertFalse(no_filter["can_show_recommendations"])
        self.assertIn("chưa xác định chắc", no_filter["polite_bot_message"])
        self.assertTrue(with_filter["unresolved_location"])
        self.assertTrue(with_filter["can_show_recommendations"])
        self.assertIn("hotel", with_filter["slots"]["accommodation_types"])
        self.assertIn("Riêng địa danh", with_filter["polite_bot_message"])
        geocode_anchor.cache_clear()

    def test_required_near_landmark_geocoder_flow_for_dinh_doc_lap(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Dinh Độc Lập",
                "lat": 10.7770,
                "lon": 106.6954,
                "display_name": "Dinh Độc Lập, Quận 1, Thành phố Hồ Chí Minh",
                "kind": "attraction",
                "default_radius_km": 2.5,
                "source": "osm",
                "provider": "osm",
                "confidence": 0.9,
                "map_area": "Quận 1",
                "address": {"city_district": "Quận 1"},
                "query": "Dinh Độc Lập, Việt Nam",
                "geocoder_queries": ["Dinh Độc Lập, Việt Nam", "Reunification Palace, Ho Chi Minh City, Vietnam"],
            },
        ) as mock_resolve:
            result = parse_user_text("khách sạn gần Dinh Độc Lập")

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["slots"]["preferred_type"], "hotel")
        self.assertEqual(result["accommodation_type"], "hotel")
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_phrase"], "Dinh Độc Lập")
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertFalse(result["unresolved_location"])
        mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_required_near_unseeded_cu_chi_geocoder_flow(self):
        geocode_anchor.cache_clear()
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Địa đạo Củ Chi",
                "lat": 11.1419,
                "lon": 106.4625,
                "display_name": "Địa đạo Củ Chi, Củ Chi, Thành phố Hồ Chí Minh",
                "kind": "attraction",
                "default_radius_km": 8.0,
                "source": "osm",
                "provider": "osm",
                "confidence": 0.87,
                "map_area": None,
                "address": {"district": "Củ Chi"},
                "query": "khu di tích địa đạo Củ Chi, Củ Chi, Hồ Chí Minh, Việt Nam",
                "geocoder_queries": ["Cu Chi Tunnels, Ho Chi Minh City, Vietnam"],
            },
        ) as mock_resolve:
            result = parse_user_text("gần khu di tích địa đạo Củ Chi")

        self.assertTrue(result["can_show_recommendations"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_phrase"], "khu di tích địa đạo Củ Chi")
        self.assertIsNotNone(result["anchor_lat"])
        self.assertIsNotNone(result["anchor_lon"])
        self.assertGreaterEqual(result["anchor_radius_km"], 5.0)
        mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_nguyen_hue_typo_query_expansion(self):
        queries = build_geocode_queries("phố đii bộ Nguyễn Huệ")

        self.assertTrue(any("Nguyen Hue Walking Street" in query for query in queries))

    def test_geocode_queries_are_hcm_bounded(self):
        queries = build_geocode_queries("Dinh Độc Lập")

        self.assertTrue(queries)
        self.assertTrue(
            all(
                any(token in query for token in ("Hồ Chí Minh", "Ho Chi Minh City", "TP Hồ Chí Minh", "Thành phố Hồ Chí Minh"))
                for query in queries
            )
        )

    def test_multi_turn_adds_near_anchor_to_existing_type(self):
        geocode_anchor.cache_clear()
        first = parse_user_text("Tôi muốn ở khách sạn")
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Dinh Độc Lập",
                "lat": 10.7770,
                "lon": 106.6954,
                "display_name": "Dinh Độc Lập, Quận 1, Thành phố Hồ Chí Minh",
                "kind": "attraction",
                "default_radius_km": 2.5,
                "source": "osm",
                "provider": "osm",
                "confidence": 0.9,
                "map_area": "Quận 1",
                "address": {"city_district": "Quận 1"},
                "query": "Dinh Độc Lập, Việt Nam",
            },
        ):
            follow_up = parse_user_text("gần Dinh Độc Lập", context_slots=first["slots"])

        self.assertEqual(follow_up["slots"]["preferred_type"], "hotel")
        self.assertEqual(follow_up["location_mode"], "near_anchor")
        self.assertEqual(follow_up["location_phrase"], "Dinh Độc Lập")
        self.assertIsNotNone(follow_up["anchor_lat"])
        self.assertTrue(follow_up["can_show_recommendations"])
        geocode_anchor.cache_clear()

    def test_location_only_context_understands_airport_anchor(self):
        first = parse_user_text("Tôi muốn tìm chỗ ở")
        follow_up = parse_user_text("Sân bay tân sơn nhất", context_slots=first["slots"])

        self.assertFalse(first["can_show_recommendations"])
        self.assertEqual(follow_up["location_mode"], "near_anchor")
        self.assertEqual(follow_up["location_phrase"], "Sân bay Tân Sơn Nhất")
        self.assertEqual(follow_up["anchor_name"], "Tân Sơn Nhất")
        self.assertTrue(follow_up["can_show_recommendations"])
        self.assertNotIn("Bạn muốn tìm chỗ ở khu vực nào", follow_up.get("polite_bot_message", ""))

    def test_airport_location_typos_and_full_sentence_use_anchor(self):
        typo = parse_user_text("Sân bay tấn sơn nhất")
        full_sentence = parse_user_text("Tôi muốn tìm chỗ ở ở sân bay tân sơn nhất")

        self.assertEqual(typo["location_mode"], "near_anchor")
        self.assertEqual(typo["location_phrase"], "Sân bay Tân Sơn Nhất")
        self.assertEqual(full_sentence["location_mode"], "near_anchor")
        self.assertEqual(full_sentence["location_phrase"], "Sân bay Tân Sơn Nhất")
        self.assertIsNone(full_sentence["canonical_area"])

    def test_accommodation_type_aliases_and_multi_type_or_slots(self):
        hostel = parse_user_text("ở trọ")
        homstay = parse_user_text("Ở homstay")
        honestay = parse_user_text("honestay")
        homestate = parse_user_text("Homestate")
        multi = parse_user_text("Homestay, trọ")

        self.assertIn("hostel", hostel["slots"]["accommodation_types"])
        self.assertIn("homestay", homstay["slots"]["accommodation_types"])
        self.assertIn("homestay", honestay["slots"]["accommodation_types"])
        self.assertIn("homestay", homestate["slots"]["accommodation_types"])
        self.assertTrue(homestate["can_show_recommendations"])
        self.assertEqual(multi["slots"]["accommodation_types"], ["homestay", "hostel"])
        self.assertIn("accommodation_types", multi["available_slots"])

    def test_budget_range_summary_keeps_min_and_max(self):
        result = parse_user_text("ở đâu cũng được giá tầm 2 đến 5 triệu")

        self.assertEqual(result["location_mode"], "anywhere")
        self.assertEqual(result["slots"]["budget_min"], 2_000_000)
        self.assertEqual(result["slots"]["budget_max"], 5_000_000)
        self.assertIn("2.000.000đ - 5.000.000đ/đêm", result["confirm_table"][1]["display_value"])
        self.assertIn("2.000.000đ - 5.000.000đ/đêm", result["soft_filter_summary"])

    def test_multi_turn_type_update_keeps_anywhere_and_budget_without_geocoder(self):
        geocode_anchor.cache_clear()
        first = parse_user_text("ở đâu cũng được giá tầm 2 đến 5 triệu", include_debug=True)
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            follow_up = parse_user_text("homstay", context_slots=first["slots"], include_debug=True)

        self.assertEqual(follow_up["location_mode"], "anywhere")
        self.assertEqual(follow_up["slots"]["budget_min"], 2_000_000)
        self.assertEqual(follow_up["slots"]["budget_max"], 5_000_000)
        self.assertIn("homestay", follow_up["slots"]["accommodation_types"])
        self.assertFalse(follow_up["geocoder_called"])
        mock_resolve.assert_not_called()

    def test_confirm_table_hides_internal_location_and_duplicate_type_keys(self):
        result = parse_user_text("khách sạn gần Tân Sơn Nhất")

        keys = [item["key"] for item in result["confirm_table"]]
        labels = [item["label"] for item in result["confirm_table"]]

        self.assertEqual(keys.count("preferred_type"), 1)
        self.assertNotIn("accommodation_type", keys)
        self.assertNotIn("location_phrase", keys)
        self.assertNotIn("location_mode", keys)
        self.assertNotIn("Địa điểm", labels)
        self.assertNotIn("Kiểu vị trí", labels)
        self.assertEqual(labels.count("Loại chỗ ở"), 1)

    def test_bare_place_follow_up_uses_current_search_context(self):
        geocode_anchor.cache_clear()
        first = parse_user_text("Tôi muốn ở khách sạn")
        with patch(
            "chat_api.filter_tree.resolve_place_reference",
            return_value={
                "name": "Dinh Độc Lập",
                "lat": 10.7770,
                "lon": 106.6954,
                "display_name": "Dinh Độc Lập, Quận 1, Thành phố Hồ Chí Minh",
                "kind": "attraction",
                "default_radius_km": 2.5,
                "source": "osm",
                "provider": "osm",
                "confidence": 0.9,
                "map_area": "Quận 1",
                "address": {"city_district": "Quận 1"},
                "query": "Dinh Độc Lập, Việt Nam",
            },
        ) as mock_resolve:
            follow_up = parse_user_text("Dinh Độc Lập", context_slots=first["slots"])

        self.assertEqual(follow_up["slots"]["preferred_type"], "hotel")
        self.assertEqual(follow_up["location_mode"], "near_anchor")
        self.assertEqual(follow_up["location_phrase"], "Dinh Độc Lập")
        self.assertIsNotNone(follow_up["anchor_lat"])
        mock_resolve.assert_called_once()
        geocode_anchor.cache_clear()

    def test_unresolved_near_landmark_blocks_recommendation(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference", return_value=None):
            result = parse_user_text("gần abcxyz không có thật")

        self.assertFalse(result["can_show_recommendations"])
        self.assertTrue(result["unresolved_location"])
        self.assertEqual(result["location_mode"], "near_anchor")
        self.assertEqual(result["location_status"], "unresolved")
        self.assertIsNone(result["anchor_lat"])
        self.assertIsNone(result["anchor_lon"])
        self.assertIn("Mình chưa xác định chắc địa điểm này", result["polite_bot_message"])
        geocode_anchor.cache_clear()

    def test_pending_unresolved_anchor_is_not_dropped_when_user_adds_type(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference", return_value=None):
            first = parse_user_text("gần abcxyz không có thật")
            follow_up = parse_user_text("Tôi muốn ở khách sạn", context_slots=first["slots"])

        self.assertEqual(follow_up["slots"]["preferred_type"], "hotel")
        self.assertEqual(follow_up["location_mode"], "near_anchor")
        self.assertEqual(follow_up["location_phrase"], "abcxyz không có thật")
        self.assertTrue(follow_up["unresolved_location"])
        self.assertTrue(follow_up["can_show_recommendations"])
        geocode_anchor.cache_clear()

    def test_multiple_location_choice_is_not_anywhere(self):
        result = parse_user_text("Hà Nội hoặc TP HCM đều được")

        self.assertFalse(result["can_show_recommendations"])
        self.assertFalse(result["explicit_anywhere"])
        self.assertEqual(result["location_mode"], "multiple_choice")

    def test_ambiguous_university_does_not_autoresolve(self):
        geocode_anchor.cache_clear()
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            result = parse_user_text("Đại học", include_debug=True)

        self.assertTrue(result["ambiguous_location"])
        self.assertFalse(result["can_show_recommendations"])
        self.assertNotEqual(result.get("canonical_area"), "Đại học Quốc gia Hà Nội")
        self.assertFalse(result["geocoder_called"])
        self.assertIn("trường đại học", result["follow_up_question"])
        mock_resolve.assert_not_called()

    def test_existing_type_keeps_recommendation_for_ambiguous_university(self):
        geocode_anchor.cache_clear()
        first = parse_user_text("homestay")
        with patch("chat_api.filter_tree.resolve_place_reference") as mock_resolve:
            follow_up = parse_user_text("Đại học", context_slots=first["slots"], include_debug=True)

        self.assertIn("homestay", follow_up["slots"]["accommodation_types"])
        self.assertTrue(follow_up["ambiguous_location"])
        self.assertTrue(follow_up["can_show_recommendations"])
        self.assertFalse(follow_up["geocoder_called"])
        mock_resolve.assert_not_called()


class RecommendationRadiusIntegrationTests(TestCase):
    def _accommodation(
        self,
        name: str,
        *,
        lat: float,
        lon: float,
        price: int = 900_000,
        rating: float = 4.2,
    ) -> Accommodation:
        return Accommodation.objects.create(
            name=name,
            accommodation_type="hotel",
            area="Quận 1",
            address=f"{name} address",
            price_per_night=price,
            capacity=2,
            rating=rating,
            review_count=10,
            amenities=["parking", "wifi"],
            latitude=lat,
            longitude=lon,
        )

    def test_recommendation_filters_by_anchor_radius_and_attaches_distance(self):
        near = self._accommodation("Near Bui Vien", lat=10.7680, lon=106.6933)
        self._accommodation("Far Bui Vien", lat=10.8200, lon=106.7600)
        preference = UserPreference.objects.create(
            area=None,
            budget=1_500_000,
            guest_count=1,
            preferred_type="hotel",
            required_amenities=["parking"],
            location_mode="near_anchor",
            location_label="gần Bùi Viện trong bán kính 2km",
            user_latitude=10.7678,
            user_longitude=106.6931,
            search_radius_km=2.0,
            filter_tree_json={
                "location": {"mode": "near_anchor"},
                "search_origin": {
                    "type": "anchor",
                    "label": "gần Bùi Viện trong bán kính 2km",
                    "latitude": 10.7678,
                    "longitude": 106.6931,
                    "radius_km": 2.0,
                },
            },
        )

        candidates = get_candidate_accommodations(preference)

        self.assertEqual(candidates, [near])
        self.assertTrue(hasattr(candidates[0], "distance_km"))
        self.assertLess(candidates[0].distance_km, 2.0)


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
        self.assertIn("protected_spans", data)
        self.assertIn("location_meta", data)
        self.assertIn("clarification", data)
        self.assertIn("eligible", data["recommendation_action"])
        self.assertTrue(data["recommendation_action"]["eligible"])
        self.assertTrue(data["recommendation_action"]["requires_submit"])
        self.assertIsNone(data["recommendation_action"]["url"])
        self.assertIn("slot_confidence", data)

    def test_api_contract_for_type_only_soft_filter(self):
        response = self.client.post(
            "/api/chat/parse/",
            data=json.dumps({"text": "homestay"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("homestay", data["slots"]["accommodation_types"])
        self.assertTrue(data["can_show_recommendations"])
        self.assertFalse(data["geocoder_called"])
        self.assertEqual(data["location_meta"]["geocoder_called"], False)
        self.assertEqual(data["location_meta"]["origin_type"], "none")
        self.assertEqual(data["search_origin"]["type"], "none")
        self.assertEqual(data["slot_confidence"]["accommodation_types"]["status"], "accepted")
        self.assertTrue(data["recommendation_action"]["eligible"])
        self.assertTrue(data["recommendation_action"]["requires_submit"])
        self.assertIsNone(data["recommendation_action"]["url"])

    def test_standalone_generic_locations_do_not_auto_geocode(self):
        for text in ["Đại học", "Sân bay", "Trung tâm"]:
            with self.subTest(text=text):
                response = self.client.post(
                    "/api/chat/parse/",
                    data=json.dumps({"text": text}),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertFalse(data["geocoder_called"])
                self.assertEqual(data["location_meta"]["geocoder_called"], False)

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

    def test_submit_selected_map_candidate_confirms_near_anchor(self):
        selected_place = {
            "name": "Nhà hát Hòa Bình",
            "display_name": "Nhà hát Hòa Bình, Công trường Lam Sơn, Thành phố Hồ Chí Minh, Việt Nam",
            "kind": "theatre",
            "lat": 10.7767437,
            "lon": 106.7032488,
            "default_radius_km": 2.5,
            "source": "osm",
            "provider": "osm",
            "address": {
                "amenity": "Nhà hát Hòa Bình",
                "road": "Công trường Lam Sơn",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                "country_code": "vn",
            },
        }
        bridge_payload = {
            "pref_id": 321,
            "recommendation_url": "/recommendations/result/321/",
            "used_default_slots": {},
        }

        with patch("chat_api.views.create_preference_from_parse", return_value=bridge_payload):
            response = self.client.post(
                "/chat_api/submit/",
                data=json.dumps(
                    {
                        "context_slots": {"preferred_type": "hotel", "accommodation_types": ["hotel"]},
                        "quick_reply_payload": {
                            "location_mode": "near_anchor",
                            "location_phrase": "Nhà hát Hòa Bình",
                            "selected_place": selected_place,
                        },
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["location_status"], "ok")
        self.assertEqual(data["location_mode"], "near_anchor")
        self.assertEqual(data["anchor_name"], "Nhà hát Hòa Bình")
        self.assertEqual(data["anchor_kind"], "theatre")
        self.assertEqual(data["anchor_lat"], 10.7767437)
        self.assertEqual(data["anchor_lon"], 106.7032488)
        self.assertEqual(data["location_candidates"], [])
        self.assertTrue(data["created_preference"])

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


class PlaceReferenceCacheTests(TestCase):
    @patch("chat_api.services.geocoder._fetch_osm")
    def test_resolve_place_reference_caches_osm_result(self, mock_fetch_osm):
        mock_fetch_osm.return_value = [
            {
                "lat": 10.7731,
                "lon": 106.7031,
                "display_name": "Phố đi bộ Nguyễn Huệ, Quận 1, Thành phố Hồ Chí Minh",
                "address": {"city_district": "Quận 1", "city": "Thành phố Hồ Chí Minh"},
                "place_id": 123,
                "type": "pedestrian",
                "class": "highway",
                "importance": 0.7,
            }
        ]

        result = resolve_place_reference("Phố đi bộ Nguyễn Huệ")

        self.assertIsNotNone(result)
        self.assertEqual(result["lat"], 10.7731)
        self.assertEqual(result["map_area"], "Quận 1")
        self.assertEqual(PlaceReference.objects.count(), 1)

        mock_fetch_osm.reset_mock()
        cached = resolve_place_reference("Phố đi bộ Nguyễn Huệ")

        self.assertEqual(cached["source"], "cache")
        mock_fetch_osm.assert_not_called()

    @patch("chat_api.services.geocoder._fetch_osm")
    def test_geocoder_rejects_outside_hcm_result(self, mock_fetch_osm):
        mock_fetch_osm.return_value = [
            {
                "lat": 21.0285,
                "lon": 105.8542,
                "display_name": "Dinh Độc Lập, Hà Nội",
                "address": {"city": "Hà Nội"},
                "place_id": 456,
                "type": "attraction",
                "class": "tourism",
                "importance": 0.9,
            }
        ]

        result = resolve_place_reference("Dinh Độc Lập")

        self.assertIsNone(result)
        self.assertEqual(PlaceReference.objects.count(), 0)

    @patch("chat_api.services.geocoder._fetch_osm")
    def test_geocoder_rejects_blocked_poi_category(self, mock_fetch_osm):
        mock_fetch_osm.return_value = [
            {
                "lat": 10.775,
                "lon": 106.701,
                "display_name": "Làng Đại Học Cafe, Thành phố Hồ Chí Minh",
                "address": {"city": "Thành phố Hồ Chí Minh"},
                "place_id": 789,
                "type": "cafe",
                "class": "amenity",
                "importance": 0.9,
            }
        ]

        result = resolve_place_reference("Làng đại học")

        self.assertIsNone(result)
        self.assertEqual(PlaceReference.objects.count(), 0)

    @patch("chat_api.services.geocoder._fetch_osm")
    def test_required_place_cache_miss_then_hit(self, mock_fetch_osm):
        mock_fetch_osm.return_value = [
            {
                "lat": 10.763,
                "lon": 106.635,
                "display_name": "Đầm Sen, Thành phố Hồ Chí Minh",
                "address": {"city": "Thành phố Hồ Chí Minh"},
                "place_id": 321,
                "type": "attraction",
                "class": "tourism",
                "importance": 0.8,
            }
        ]

        first = resolve_place_reference("Đầm Sen")

        self.assertIsNotNone(first)
        self.assertEqual(PlaceReference.objects.count(), 1)
        self.assertEqual(mock_fetch_osm.call_count, 1)

        mock_fetch_osm.reset_mock()
        second = resolve_place_reference("Đầm Sen")

        self.assertEqual(second["source"], "cache")
        mock_fetch_osm.assert_not_called()

    def test_required_validator_rejects_bad_candidates(self):
        outside = validate_geocode_candidate(
            {
                "lat": 21.0285,
                "lon": 105.8542,
                "display_name": "Dinh Độc Lập, Hà Nội",
                "type": "attraction",
                "address": {"city": "Hà Nội"},
            },
            query="Dinh Độc Lập",
        )
        wrong_alias = validate_geocode_candidate(
            {
                "lat": 10.84,
                "lon": 106.75,
                "display_name": "Một địa điểm khác, Thủ Đức, Thành phố Hồ Chí Minh",
                "type": "attraction",
                "address": {"city": "Thành phố Hồ Chí Minh"},
            },
            query="Dinh Độc Lập",
        )
        cafe = validate_geocode_candidate(
            {
                "lat": 10.77,
                "lon": 106.69,
                "display_name": "Đầm Sen Cafe, Thành phố Hồ Chí Minh",
                "type": "cafe",
                "address": {"city": "Thành phố Hồ Chí Minh"},
            },
            query="Đầm Sen",
        )
        unrelated_bus_stop = validate_geocode_candidate(
            {
                "lat": 10.77,
                "lon": 106.69,
                "name": "Trạm xe buýt Hàm Nghi",
                "display_name": "Trạm xe buýt Hàm Nghi, Thành phố Hồ Chí Minh",
                "type": "bus_stop",
                "class": "highway",
                "address": {"city": "Thành phố Hồ Chí Minh"},
            },
            query="Bitexco",
        )
        low_match = validate_geocode_candidate(
            {
                "lat": 10.77,
                "lon": 106.69,
                "display_name": "Nhà hát Thành phố Hồ Chí Minh",
                "type": "theatre",
                "address": {"city": "Thành phố Hồ Chí Minh"},
            },
            query="Snow Town Sài Gòn",
        )
        ambiguous = validate_geocode_candidate(
            {
                "lat": 10.77,
                "lon": 106.69,
                "display_name": "Đầm Sen, Thành phố Hồ Chí Minh",
                "type": "attraction",
                "address": {"city": "Thành phố Hồ Chí Minh"},
            },
            query="Đầm Sen",
            top_score=0.84,
            runner_up_score=0.80,
        )

        self.assertFalse(outside.accepted)
        self.assertEqual(outside.reason, "outside_hcm")
        self.assertFalse(wrong_alias.accepted)
        self.assertIn(wrong_alias.reason, {"low_name_match", "known_alias_mismatch"})
        self.assertFalse(cafe.accepted)
        self.assertTrue(cafe.reason.startswith("blocked_category"))
        self.assertFalse(unrelated_bus_stop.accepted)
        self.assertIn(unrelated_bus_stop.reason, {"low_name_match", "blocked_category:bus_stop"})
        self.assertFalse(low_match.accepted)
        self.assertEqual(low_match.reason, "low_name_match")
        self.assertFalse(ambiguous.accepted)
        self.assertEqual(ambiguous.reason, "top1_top2_margin_too_small")


class SubmitMessagePreferenceTests(TestCase):
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
        self.assertTrue(data["recommendation_action"]["visible"])
        self.assertTrue(data["recommendation_action"]["enabled"])
        self.assertTrue(data["recommendation_action"]["eligible"])
        self.assertEqual(data["recommendation_action"]["pref_id"], 123)
        self.assertEqual(data["recommendation_action"]["url"], "/recommendations/result/123/")
        self.assertFalse(data["recommendation_action"]["requires_submit"])
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

    def test_submit_type_only_uses_recommendation_action_contract(self):
        bridge_payload = {
            "pref_id": 789,
            "recommendation_url": "/recommendations/result/789/",
            "used_default_slots": {
                "budget": {"value": 0, "reason": "user_missing_budget_no_budget_filter"},
                "guest_count": {"value": 1, "reason": "user_missing_guest_count_safe_minimum"},
            },
        }
        with patch("chat_api.views.create_preference_from_parse", return_value=bridge_payload) as mock_bridge:
            response = self.client.post(
                "/chat_api/submit/",
                data=json.dumps({"text": "homestay"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("homestay", data["slots"]["accommodation_types"])
        self.assertTrue(data["can_show_recommendations"])
        self.assertEqual(data["usable_filters"], ["accommodation_types"])
        self.assertTrue(data["recommendation_action"]["enabled"])
        self.assertTrue(data["recommendation_action"]["eligible"])
        self.assertEqual(data["recommendation_action"]["pref_id"], 789)
        self.assertFalse(data["recommendation_action"]["requires_submit"])
        self.assertEqual(data["recommendation_action"]["reason"], "preference_created")
        self.assertFalse(data["geocoder_called"])
        mock_bridge.assert_called_once()

    def test_submit_location_only_airport_creates_recommendation_action(self):
        response = self.client.post(
            "/chat_api/submit/",
            data=json.dumps({"text": "Sân bay tân sơn nhất"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["created_preference"])
        self.assertEqual(data["location_mode"], "near_anchor")
        self.assertEqual(data["anchor_name"], "Tân Sơn Nhất")
        self.assertEqual(data["usable_filters"], ["location"])
        self.assertTrue(data["recommendation_action"]["eligible"])
        self.assertFalse(data["recommendation_action"]["requires_submit"])
        self.assertTrue(data["recommendation_action"]["url"])
        self.assertEqual(data["search_origin"]["type"], "anchor")
        self.assertEqual(data["location_meta"]["origin_type"], "anchor")
        preference = UserPreference.objects.get(pk=data["pref_id"])
        self.assertEqual(preference.filter_tree_json["search_origin"]["type"], "anchor")

    def test_browser_geolocation_is_user_location_origin(self):
        response = self.client.post(
            "/chat_api/submit/",
            data=json.dumps(
                {
                    "text": "gần tôi",
                    "user_location": {"lat": 10.78, "lon": 106.70, "accuracy": 20},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["search_origin"]["type"], "user_location")
        self.assertEqual(data["location_meta"]["origin_type"], "user_location")
        self.assertTrue(data["recommendation_action"]["eligible"])
        self.assertFalse(data["recommendation_action"]["requires_submit"])

    def test_submit_ambiguous_location_without_filters_disables_action(self):
        response = self.client.post(
            "/chat_api/submit/",
            data=json.dumps({"text": "Đại học"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ambiguous_location"])
        self.assertFalse(data["can_show_recommendations"])
        self.assertFalse(data["recommendation_action"]["enabled"])
        self.assertFalse(data["recommendation_action"]["eligible"])
        self.assertEqual(data["recommendation_action"]["reason"], "ambiguous_location")


class RecommendationResultContractTests(TestCase):
    def test_recommendation_result_uses_pagination_without_top_five_cutoff(self):
        for index in range(7):
            Accommodation.objects.create(
                name=f"Chatbot Hotel {index}",
                accommodation_type="hotel",
                area="Quận 1",
                address=f"{index} Nguyễn Huệ",
                price_per_night=700_000 + index,
                capacity=2,
                rating=4.0,
                amenities=["wifi"],
                latitude=10.77,
                longitude=106.70,
            )
        preference = UserPreference.objects.create(
            area=None,
            budget=0,
            guest_count=1,
            preferred_type=None,
            location_mode="unknown",
            filter_tree_json={},
        )

        response = self.client.get(f"/recommendations/{preference.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.per_page, 10)
        self.assertEqual(response.context["total_results"], 7)
        self.assertEqual(len(response.context["results"]), 7)


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
        self.assertTrue(result["ready_for_recommendation"])
        self.assertFalse(result["confirmation_required"])
        self.assertEqual(result["location_mode"], "city_center")
        self.assertNotIn("area", result["missing_slots"])
        self.assertEqual(result["parser_mode"], "deterministic_fuzzy_fast")
