"""
Tests that parse_user_text() backward-compatible response shape is unchanged.

Mandatory case (spec):
  11. parse_user_text response shape cũ không đổi

Run:  python manage.py test chat_api.tests.test_legacy_parse_adapter
"""
from unittest.mock import patch

from django.test import SimpleTestCase

_NEAR_ANCHOR = "chat_api.location.strategies.near_anchor._lookup_place_reference"
_FALLBACK = "chat_api.location.strategies.fallback_geocode._geocode"

# Keys guaranteed present in every parse_user_text() response.
# Keys that must be present in ALL parse_user_text() responses (including greeting).
REQUIRED_KEYS = frozenset({
    "schema_version",
    "intent",
    "conversation_intent",
    "slots",
    "missing_slots",
    "suggested_questions",
    "ready_for_recommendation",
    "should_ask_optional",
    "follow_up_question",
    "parser_mode",
    "location_status",
    "location_candidates",
    "canonical_area",
    "location_confidence",
    "location_source",
    "matched_text",
    "assumptions",
    "used_default_slots",
    "llm_called",
    "router",
})

# Keys present in non-greeting search paths only.
SEARCH_PATH_KEYS = frozenset({"input_type", "input_classification"})

REQUIRED_SLOT_KEYS = frozenset({
    "area",
    "guest_count",
    "budget",
    "budget_min",
    "budget_max",
    "trip_days",
    "required_amenities",
    "accommodation_types",
})

VALID_LOCATION_STATUSES = frozenset({
    "ok", "unresolved", "ambiguous", "conflict", "multiple_choice", "unsupported",
})


def _parse(text, **kw):
    from chat_api.parser_service import parse_user_text
    return parse_user_text(text, **kw)


class TestParseResponseShape(SimpleTestCase):
    """Test 11 — response shape must be stable."""

    def _assert_required_keys(self, result: dict, text: str) -> None:
        missing = REQUIRED_KEYS - set(result.keys())
        self.assertEqual(missing, set(), msg=f"Missing keys for {text!r}: {missing}")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_anywhere_has_required_keys(self, *_):
        result = _parse("ở đâu cũng được")
        self._assert_required_keys(result, "ở đâu cũng được")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_budget_only_has_required_keys(self, *_):
        result = _parse("dưới 500k")
        self._assert_required_keys(result, "dưới 500k")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_amenity_only_has_required_keys(self, *_):
        result = _parse("có wifi")
        self._assert_required_keys(result, "có wifi")

    @patch(_NEAR_ANCHOR, return_value={"canonical_name": "landmark 81",
                                       "latitude": 10.82, "longitude": 106.72,
                                       "display_name": "Landmark 81", "default_radius_km": 5.0})
    @patch(_FALLBACK, return_value=None)
    def test_landmark_query_has_required_keys(self, *_):
        result = _parse("gần Landmark 81")
        self._assert_required_keys(result, "gần Landmark 81")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_area_query_has_required_keys(self, *_):
        result = _parse("Quận 3")
        self._assert_required_keys(result, "Quận 3")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_greeting_has_required_keys(self, *_):
        result = _parse("xin chào")
        self._assert_required_keys(result, "xin chào")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_search_path_has_input_type(self, *_):
        # input_type / input_classification only present on non-greeting paths
        result = _parse("Quận 3")
        for key in SEARCH_PATH_KEYS:
            self.assertIn(key, result, msg=f"Key missing from search path: {key}")


class TestParseSlotShape(SimpleTestCase):
    """Slots dict must always include the required subset of keys."""

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_slots_has_required_keys(self, *_):
        result = _parse("ở đâu cũng được 300k cho 2 người 3 ngày có wifi")
        slots = result.get("slots", {})
        for key in REQUIRED_SLOT_KEYS:
            self.assertIn(key, slots, msg=f"Slot key missing: {key}")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_slots_budget_extracted(self, *_):
        result = _parse("dưới 1tr2")
        self.assertEqual(result["slots"].get("budget_max"), 1_200_000)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_slots_guest_count_extracted(self, *_):
        result = _parse("cho 3 người")
        self.assertEqual(result["slots"].get("guest_count"), 3)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_slots_amenities_extracted(self, *_):
        result = _parse("có wifi có hồ bơi")
        self.assertIn("wifi", result["slots"].get("required_amenities", []))
        self.assertIn("pool", result["slots"].get("required_amenities", []))


class TestLocationStatusValues(SimpleTestCase):

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_location_status_is_valid(self, *_):
        queries = [
            "ở đâu cũng được",
            "Quận 3",
            "có wifi",
            "xin chào",
        ]
        for q in queries:
            result = _parse(q)
            status = result.get("location_status")
            self.assertIn(status, VALID_LOCATION_STATUSES, msg=f"Invalid status for {q!r}: {status}")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_area_query_location_status_ok(self, *_):
        result = _parse("Quận 3")
        self.assertEqual(result["location_status"], "ok")

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_amenity_only_location_status_unresolved(self, *_):
        result = _parse("có wifi")
        self.assertIn(result["location_status"], {"unresolved", "ok"})


class TestParseTypedValues(SimpleTestCase):

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_schema_version_is_string(self, *_):
        result = _parse("ở đâu cũng được")
        self.assertIsInstance(result["schema_version"], str)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_llm_called_is_bool(self, *_):
        result = _parse("ở đâu cũng được")
        self.assertIsInstance(result["llm_called"], bool)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_ready_for_recommendation_is_bool(self, *_):
        result = _parse("ở đâu cũng được")
        self.assertIsInstance(result["ready_for_recommendation"], bool)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_suggested_questions_is_list(self, *_):
        result = _parse("ở đâu cũng được")
        self.assertIsInstance(result["suggested_questions"], list)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_missing_slots_is_list(self, *_):
        result = _parse("ở đâu cũng được")
        self.assertIsInstance(result["missing_slots"], list)

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_input_type_is_string(self, *_):
        result = _parse("ở đâu cũng được")
        self.assertIsInstance(result["input_type"], str)
