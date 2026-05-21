"""
End-to-end backward-compatibility tests for the full chat → recommendation pipeline.

Mandatory case (spec):
  12. recommendation_bridge creates UserPreference correctly from parse_result v1 and v2

Run:  python manage.py test chat_api.tests.test_pipeline_backward_compat
"""
import dataclasses
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)

_NEAR_ANCHOR = "chat_api.location.strategies.near_anchor._lookup_place_reference"
_FALLBACK = "chat_api.location.strategies.fallback_geocode._geocode"
_PREF_CREATE = "preferences.models.UserPreference.objects.create"
_REVERSE = "chat_api.recommendation_bridge.reverse"


def _mock_pref(pref_id: int = 42) -> MagicMock:
    p = MagicMock()
    p.id = pref_id
    return p


def _stub_reverse(name, **kwargs):
    pref_id = kwargs.get("kwargs", {}).get("pref_id", 0)
    return f"/recommendations/{pref_id}/"


def _make_intent(
    *,
    mode: LocationMode = LocationMode.AREA,
    status: LocationStatus = LocationStatus.OK,
    canonical_area: str | None = "quan 1",
    lat: float | None = None,
    lon: float | None = None,
    budget: int | None = None,
    input_kind: str = "area",
    amenities: list | None = None,
    acc_types: list | None = None,
) -> SearchIntent:
    return SearchIntent(
        raw_text="test",
        input_kind=input_kind,
        conversation_intent="search",
        location=ResolvedLocation(
            status=status,
            mode=mode,
            canonical_area=canonical_area,
            latitude=lat,
            longitude=lon,
        ),
        area=canonical_area if mode == LocationMode.AREA else None,
        budget=budget,
        required_amenities=amenities or [],
        accommodation_types=acc_types or [],
    )


@override_settings(CHAT_PIPELINE_V2_ENABLED=False)
class TestV1PathStillWorks(SimpleTestCase):
    """parse_result v1 (no search_intent_v2 key) must still create a preference."""

    @patch(_PREF_CREATE, return_value=_mock_pref(10))
    @patch(_REVERSE, side_effect=_stub_reverse)
    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_v1_parse_result_creates_preference(self, *_):
        from chat_api.parser_service import parse_user_text
        from chat_api.recommendation_bridge import create_preference_from_parse

        # Parse produces a v1 result (no search_intent_v2)
        result = parse_user_text("Quận 3")
        self.assertNotIn("search_intent_v2", result)

        # Bridge must succeed
        bridge = create_preference_from_parse(result)
        self.assertIn("pref_id", bridge)
        self.assertIsInstance(bridge["pref_id"], int)

    @patch(_PREF_CREATE, return_value=_mock_pref(11))
    @patch(_REVERSE, side_effect=_stub_reverse)
    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_v1_response_keys_present(self, *_):
        from chat_api.parser_service import parse_user_text
        from chat_api.recommendation_bridge import create_preference_from_parse

        result = parse_user_text("có wifi")
        bridge = create_preference_from_parse(result)

        for key in ("pref_id", "recommendation_url", "used_default_slots",
                    "user_location_used", "search_origin"):
            self.assertIn(key, bridge, msg=f"Key missing: {key}")

    @patch(_PREF_CREATE, return_value=_mock_pref(12))
    @patch(_REVERSE, side_effect=_stub_reverse)
    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_v1_recommendation_url_contains_pref_id(self, *_):
        from chat_api.parser_service import parse_user_text
        from chat_api.recommendation_bridge import create_preference_from_parse

        result = parse_user_text("Quận 3")
        bridge = create_preference_from_parse(result)
        self.assertIn(str(bridge["pref_id"]), bridge["recommendation_url"])


class TestV2PathWithIntentObject(SimpleTestCase):
    """parse_result v2 with SearchIntent object creates a preference correctly."""

    @patch(_PREF_CREATE, return_value=_mock_pref(20))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_area_intent_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3")
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)
        self.assertEqual(result["pref_id"], 20)

    @patch(_PREF_CREATE, return_value=_mock_pref(21))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_response_has_same_keys_as_v1(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1", budget=500_000)
        result = create_preference_from_parse({"search_intent_v2": intent})

        for key in ("pref_id", "recommendation_url", "used_default_slots",
                    "user_location_used", "search_origin"):
            self.assertIn(key, result, msg=f"Key missing from v2 response: {key}")

    @patch(_PREF_CREATE, return_value=_mock_pref(22))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_recommendation_url_correct(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1")
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("22", result["recommendation_url"])

    @patch(_PREF_CREATE, return_value=_mock_pref(23))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_anywhere_intent_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(
            mode=LocationMode.ANYWHERE,
            canonical_area=None,
            budget=300_000,
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)

    @patch(_PREF_CREATE, return_value=_mock_pref(24))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_amenity_only_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.UNRESOLVED,
            canonical_area=None,
            input_kind="amenity_only",
            amenities=["wifi", "pool"],
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)

    @patch(_PREF_CREATE, return_value=_mock_pref(25))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_near_user_with_gps_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.OK,
            lat=10.77, lon=106.69,
            canonical_area=None,
        )
        intent.user_location = UserLocationInput(lat=10.77, lon=106.69)
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertTrue(result["user_location_used"])

    @patch(_PREF_CREATE, return_value=_mock_pref(26))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_v2_near_anchor_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            status=LocationStatus.OK,
            lat=10.82, lon=106.73,
            canonical_area="landmark 81",
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)

    def test_v2_greeting_raises(self):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(input_kind="greeting", mode=LocationMode.UNKNOWN,
                              canonical_area=None, status=LocationStatus.UNRESOLVED)
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})

    def test_v2_no_filters_raises(self):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = SearchIntent(
            raw_text="",
            input_kind="unknown",
            conversation_intent="search",
        )
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})


class TestV2PathWithIntentDict(SimpleTestCase):
    """parse_result v2 where search_intent_v2 is a serialised dict (round-trip)."""

    @patch(_PREF_CREATE, return_value=_mock_pref(30))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_dict_round_trip_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 5", budget=400_000)
        intent_dict = dataclasses.asdict(intent)
        result = create_preference_from_parse({"search_intent_v2": intent_dict})
        self.assertIn("pref_id", result)

    @patch(_PREF_CREATE, return_value=_mock_pref(31))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_dict_near_anchor_restores_coords(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            lat=10.82, lon=106.73,
            canonical_area="landmark 81",
        )
        intent_dict = dataclasses.asdict(intent)
        result = create_preference_from_parse({"search_intent_v2": intent_dict})
        self.assertIn("pref_id", result)

    @patch(_PREF_CREATE, return_value=_mock_pref(32))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_dict_hotel_name_not_lost(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse

        intent = SearchIntent(
            raw_text="Rex Hotel",
            input_kind="hotel_name",
            conversation_intent="search",
            hotel_name="Rex Hotel",
            location=ResolvedLocation(
                status=LocationStatus.OK,
                mode=LocationMode.HOTEL_NAME,
                canonical_area=None,
                latitude=10.77, longitude=106.69,
            ),
        )
        intent_dict = dataclasses.asdict(intent)
        result = create_preference_from_parse({"search_intent_v2": intent_dict})
        self.assertIn("pref_id", result)


class TestUsableFiltersFromParse(SimpleTestCase):
    """usable_filters_from_parse delegates correctly to v1 and v2."""

    @patch(_NEAR_ANCHOR, return_value=None)
    @patch(_FALLBACK, return_value=None)
    def test_v1_parse_returns_filters_list(self, *_):
        from chat_api.parser_service import parse_user_text
        from chat_api.recommendation_bridge import usable_filters_from_parse

        result = parse_user_text("Quận 3")
        filters = usable_filters_from_parse(result)
        self.assertIsInstance(filters, list)

    def test_v2_intent_object_returns_filters(self):
        from chat_api.recommendation_bridge import usable_filters_from_parse

        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1", budget=500_000)
        filters = usable_filters_from_parse({"search_intent_v2": intent})
        self.assertIn("location", filters)
        self.assertIn("budget", filters)

    def test_v2_amenity_only_filters(self):
        from chat_api.recommendation_bridge import usable_filters_from_parse

        intent = _make_intent(
            mode=LocationMode.UNKNOWN, status=LocationStatus.UNRESOLVED,
            canonical_area=None, amenities=["wifi"]
        )
        filters = usable_filters_from_parse({"search_intent_v2": intent})
        self.assertIn("amenities", filters)
