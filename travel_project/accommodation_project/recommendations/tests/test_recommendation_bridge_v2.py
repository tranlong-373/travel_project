"""
Tests for recommendation_bridge v2 path.

Mandatory case (spec):
  12. recommendation_bridge creates UserPreference correctly from parse_result v1 and v2

Run:  python manage.py test recommendations.tests.test_recommendation_bridge_v2
"""
import dataclasses
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)
from chat_api.recommendation_bridge import (
    usable_filters_from_intent,
    usable_filters_from_parse,
)

_PREF_CREATE = "preferences.models.UserPreference.objects.create"
_REVERSE = "chat_api.recommendation_bridge.reverse"


def _stub_reverse(name, **kwargs):
    pref_id = kwargs.get("kwargs", {}).get("pref_id", 0)
    return f"/recommendations/{pref_id}/"


def _mock_pref(pref_id: int = 1) -> MagicMock:
    p = MagicMock()
    p.id = pref_id
    return p


def _make_intent(
    *,
    mode: LocationMode = LocationMode.AREA,
    status: LocationStatus = LocationStatus.OK,
    canonical_area: str | None = "quan 1",
    lat: float | None = None,
    lon: float | None = None,
    budget: int | None = None,
    budget_max: int | None = None,
    guest_count: int | None = None,
    amenities: list | None = None,
    acc_types: list | None = None,
    hotel_name: str | None = None,
    input_kind: str = "area",
    user_location: UserLocationInput | None = None,
    nearby_poi_key: str | None = None,
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
            nearby_poi_key=nearby_poi_key,
        ),
        area=canonical_area if mode == LocationMode.AREA else None,
        hotel_name=hotel_name,
        budget=budget,
        budget_max=budget_max,
        guest_count=guest_count,
        required_amenities=amenities or [],
        accommodation_types=acc_types or [],
        user_location=user_location,
    )


# ── usable_filters_from_intent ────────────────────────────────────────────────

class TestUsableFiltersFromIntent(SimpleTestCase):

    def test_area_mode_includes_location(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1")
        self.assertIn("location", usable_filters_from_intent(intent))

    def test_anywhere_mode_includes_location_anywhere(self):
        intent = _make_intent(mode=LocationMode.ANYWHERE, canonical_area=None)
        self.assertIn("location_anywhere", usable_filters_from_intent(intent))

    def test_near_anchor_with_coords_includes_location(self):
        intent = _make_intent(mode=LocationMode.NEAR_ANCHOR, lat=10.82, lon=106.73)
        self.assertIn("location", usable_filters_from_intent(intent))

    def test_near_anchor_without_coords_no_location(self):
        intent = _make_intent(mode=LocationMode.NEAR_ANCHOR, lat=None, lon=None)
        self.assertNotIn("location", usable_filters_from_intent(intent))

    def test_hotel_name_includes_location(self):
        intent = _make_intent(mode=LocationMode.HOTEL_NAME, hotel_name="Rex Hotel")
        self.assertIn("location", usable_filters_from_intent(intent))

    def test_budget_included(self):
        intent = _make_intent(budget=500_000)
        self.assertIn("budget", usable_filters_from_intent(intent))

    def test_amenities_included(self):
        intent = _make_intent(amenities=["wifi", "pool"])
        self.assertIn("amenities", usable_filters_from_intent(intent))

    def test_nearby_poi_key_included(self):
        intent = _make_intent(mode=LocationMode.AREA, nearby_poi_key="cafe")
        filters = usable_filters_from_intent(intent)
        self.assertIn("nearby_poi", filters)

    def test_empty_intent_returns_empty(self):
        intent = SearchIntent(raw_text="", input_kind="unknown")
        self.assertEqual(usable_filters_from_intent(intent), [])


# ── usable_filters_from_parse (v2 delegation) ─────────────────────────────────

class TestUsableFiltersFromParseV2(SimpleTestCase):

    def test_delegates_to_intent_when_v2_present(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3", budget=300_000)
        filters = usable_filters_from_parse({"search_intent_v2": intent})
        self.assertIn("location", filters)
        self.assertIn("budget", filters)

    def test_v2_dict_round_trip(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3")
        filters = usable_filters_from_parse({"search_intent_v2": dataclasses.asdict(intent)})
        self.assertIn("location", filters)

    def test_no_v2_uses_legacy_path(self):
        parse_result = {
            "location_status": "ok",
            "location_mode": "area",
            "slots": {"area": "Quận 3", "budget_max": None},
            "canonical_area": "Quận 3",
        }
        filters = usable_filters_from_parse(parse_result)
        self.assertIsInstance(filters, list)


# ── create_preference_from_parse v2 path ──────────────────────────────────────

class TestCreatePreferenceV2Area(SimpleTestCase):

    @patch(_PREF_CREATE, return_value=_mock_pref(1))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_area_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3")
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertEqual(result["pref_id"], 1)

    @patch(_PREF_CREATE, return_value=_mock_pref(2))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_area_response_keys(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1")
        result = create_preference_from_parse({"search_intent_v2": intent})
        for k in ("pref_id", "recommendation_url", "used_default_slots",
                  "user_location_used", "search_origin"):
            self.assertIn(k, result)

    @patch(_PREF_CREATE, return_value=_mock_pref(3))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_recommendation_url_contains_pref_id(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1")
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("3", result["recommendation_url"])


class TestCreatePreferenceV2NearAnchor(SimpleTestCase):

    @patch(_PREF_CREATE, return_value=_mock_pref(10))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_near_anchor_with_coords_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR, lat=10.82, lon=106.73,
            canonical_area="landmark 81",
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)

    def test_near_anchor_without_coords_raises(self):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(mode=LocationMode.NEAR_ANCHOR, lat=None, lon=None)
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})


class TestCreatePreferenceV2HotelName(SimpleTestCase):

    @patch(_PREF_CREATE, return_value=_mock_pref(20))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_hotel_name_with_coords_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME, canonical_area=None,
            hotel_name="Rex Hotel", lat=10.77, lon=106.69,
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)

    @patch(_PREF_CREATE, return_value=_mock_pref(21))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_hotel_name_stored_in_filter_tree_json(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME, canonical_area=None,
            hotel_name="Rex Hotel", lat=10.77, lon=106.69,
        )
        create_preference_from_parse({"search_intent_v2": intent})
        from preferences.models import UserPreference
        _, call_kwargs = UserPreference.objects.create.call_args
        tree = call_kwargs.get("filter_tree_json")
        self.assertIsNotNone(tree)

    @patch(_PREF_CREATE, return_value=_mock_pref(22))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_hotel_name_not_converted_to_area(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME, canonical_area=None,
            hotel_name="Rex Hotel", lat=10.77, lon=106.69,
        )
        create_preference_from_parse({"search_intent_v2": intent})
        from preferences.models import UserPreference
        _, call_kwargs = UserPreference.objects.create.call_args
        self.assertIsNone(call_kwargs.get("area"))


class TestCreatePreferenceV2NearUser(SimpleTestCase):

    @patch(_PREF_CREATE, return_value=_mock_pref(30))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_near_user_with_gps_user_location_used(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        gps = UserLocationInput(lat=10.77, lon=106.69)
        intent = _make_intent(
            mode=LocationMode.NEAR_USER, lat=10.77, lon=106.69,
            canonical_area=None, user_location=gps,
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertTrue(result["user_location_used"])


class TestCreatePreferenceV2AmenityOnly(SimpleTestCase):

    @patch(_PREF_CREATE, return_value=_mock_pref(40))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_amenity_only_creates_preference(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.UNKNOWN, status=LocationStatus.UNRESOLVED,
            canonical_area=None, input_kind="amenity_only",
            amenities=["wifi", "pool"],
        )
        result = create_preference_from_parse({"search_intent_v2": intent})
        self.assertIn("pref_id", result)

    def test_amenity_only_without_amenities_raises(self):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.UNKNOWN, status=LocationStatus.UNRESOLVED,
            canonical_area=None, input_kind="amenity_only",
            amenities=[],
        )
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})


class TestValidationBlocking(SimpleTestCase):

    def test_greeting_raises(self):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.UNKNOWN, status=LocationStatus.UNRESOLVED,
            canonical_area=None, input_kind="greeting",
        )
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})

    def test_ambiguous_location_raises(self):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(
            mode=LocationMode.AMBIGUOUS, status=LocationStatus.AMBIGUOUS,
            canonical_area=None, budget=300_000,
        )
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})


class TestDictRoundTrip(SimpleTestCase):

    @patch(_PREF_CREATE, return_value=_mock_pref(50))
    @patch(_REVERSE, side_effect=_stub_reverse)
    def test_serialised_intent_dict_works(self, *_):
        from chat_api.recommendation_bridge import create_preference_from_parse
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 7", budget=600_000)
        intent_dict = dataclasses.asdict(intent)
        result = create_preference_from_parse({"search_intent_v2": intent_dict})
        self.assertEqual(result["pref_id"], 50)
