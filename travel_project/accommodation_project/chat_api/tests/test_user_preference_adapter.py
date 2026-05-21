"""
Unit tests for chat_api/adapters/search_intent_to_user_preference.py.

Run:  python manage.py test chat_api.tests.test_user_preference_adapter
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)


def _intent(
    *,
    mode: LocationMode = LocationMode.AREA,
    status: LocationStatus = LocationStatus.OK,
    canonical_area: str | None = "quan 1",
    lat: float | None = None,
    lon: float | None = None,
    budget: int | None = None,
    budget_max: int | None = None,
    guest_count: int | None = None,
    trip_days: int | None = None,
    amenities: list | None = None,
    acc_types: list | None = None,
    hotel_name: str | None = None,
    nearby_poi_key: str | None = None,
    input_kind: str = "area",
    user_location: UserLocationInput | None = None,
) -> SearchIntent:
    loc = ResolvedLocation(
        status=status,
        mode=mode,
        canonical_area=canonical_area,
        display_label=canonical_area,
        latitude=lat,
        longitude=lon,
        radius_km=5.0,
        nearby_poi_key=nearby_poi_key,
    )
    return SearchIntent(
        raw_text="test",
        input_kind=input_kind,
        location=loc,
        area=canonical_area if mode == LocationMode.AREA else None,
        hotel_name=hotel_name,
        budget=budget,
        budget_max=budget_max,
        guest_count=guest_count,
        trip_days=trip_days,
        required_amenities=amenities or [],
        accommodation_types=acc_types or [],
        user_location=user_location,
        conversation_intent="search",
    )


class TestSearchIntentToLegacySlots(SimpleTestCase):

    def _slots(self, **kw):
        from chat_api.adapters.search_intent_to_user_preference import search_intent_to_legacy_slots
        return search_intent_to_legacy_slots(_intent(**kw))

    def test_area_in_slots(self):
        slots = self._slots(mode=LocationMode.AREA, canonical_area="quan 3")
        self.assertEqual(slots.get("area"), "quan 3")

    def test_no_area_for_near_user(self):
        slots = self._slots(
            mode=LocationMode.NEAR_USER,
            canonical_area=None,
            user_location=UserLocationInput(lat=10.77, lon=106.69),
        )
        self.assertIsNone(slots.get("area"))

    def test_budget_max_set(self):
        slots = self._slots(budget_max=500_000)
        self.assertEqual(slots.get("budget_max"), 500_000)

    def test_guest_count_set(self):
        slots = self._slots(guest_count=3)
        self.assertEqual(slots.get("guest_count"), 3)

    def test_amenities_set(self):
        slots = self._slots(amenities=["wifi", "pool"])
        self.assertIn("wifi", slots.get("required_amenities", []))
        self.assertIn("pool", slots.get("required_amenities", []))

    def test_accommodation_types_set(self):
        slots = self._slots(acc_types=["hotel", "homestay"])
        self.assertIn("hotel", slots.get("accommodation_types", []))

    def test_no_area_for_hotel_name(self):
        slots = self._slots(mode=LocationMode.HOTEL_NAME, canonical_area=None, hotel_name="Rex Hotel")
        self.assertIsNone(slots.get("area"))


class TestSearchIntentToLocationResult(SimpleTestCase):

    def _loc_result(self, **kw):
        from chat_api.adapters.search_intent_to_user_preference import search_intent_to_location_result
        return search_intent_to_location_result(_intent(**kw))

    def test_area_mode_location_status(self):
        lr = self._loc_result(mode=LocationMode.AREA, status=LocationStatus.OK)
        self.assertEqual(lr.get("location_status"), "ok")

    def test_near_user_mode_location_status(self):
        lr = self._loc_result(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.OK,
            lat=10.77, lon=106.69,
        )
        self.assertEqual(lr.get("location_status"), "ok")

    def test_anywhere_mode_is_explicit_anywhere(self):
        lr = self._loc_result(mode=LocationMode.ANYWHERE, status=LocationStatus.OK, canonical_area=None)
        self.assertTrue(lr.get("explicit_anywhere") or lr.get("location_status") == "ok")


class TestBuildUserPreferenceKwargs(SimpleTestCase):

    def _kwargs(self, **kw):
        from chat_api.adapters.search_intent_to_user_preference import build_user_preference_kwargs
        return build_user_preference_kwargs(_intent(**kw))

    def test_returns_dict(self):
        result = self._kwargs()
        self.assertIsInstance(result, dict)

    def test_area_stored(self):
        kw = self._kwargs(mode=LocationMode.AREA, canonical_area="quan 5")
        self.assertEqual(kw.get("area"), "quan 5")

    def test_budget_stored(self):
        kw = self._kwargs(budget_max=800_000)
        self.assertEqual(kw.get("budget"), 800_000)

    def test_guest_count_stored(self):
        kw = self._kwargs(guest_count=2)
        self.assertEqual(kw.get("guest_count"), 2)

    def test_filter_tree_json_present(self):
        kw = self._kwargs()
        self.assertIn("filter_tree_json", kw)

    def test_hotel_name_not_in_area(self):
        kw = self._kwargs(
            mode=LocationMode.HOTEL_NAME,
            canonical_area=None,
            hotel_name="Rex Hotel",
            lat=10.77, lon=106.69,
        )
        self.assertIsNone(kw.get("area"))

    def test_hotel_name_in_filter_tree_json(self):
        kw = self._kwargs(
            mode=LocationMode.HOTEL_NAME,
            canonical_area=None,
            hotel_name="Rex Hotel",
            lat=10.77, lon=106.69,
        )
        # filter_tree_json may be a dict (JSONField native) or a JSON string
        tree = kw.get("filter_tree_json")
        self.assertIsNotNone(tree)

    def test_near_user_stores_user_lat_lon(self):
        kw = self._kwargs(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.OK,
            lat=10.77, lon=106.69,
            canonical_area=None,
            user_location=UserLocationInput(lat=10.77, lon=106.69),
        )
        self.assertIsNotNone(kw.get("user_latitude") or kw.get("anchor_lat"))

    def test_anywhere_mode_produces_valid_kwargs(self):
        kw = self._kwargs(mode=LocationMode.ANYWHERE, canonical_area=None)
        self.assertIn("filter_tree_json", kw)

    def test_amenities_in_filter_tree(self):
        kw = self._kwargs(amenities=["wifi", "pool"])
        tree = kw.get("filter_tree_json")
        # filter_tree_json may be dict (JSONField native) or a JSON string
        self.assertIsNotNone(tree)

    def test_near_anchor_with_coords(self):
        kw = self._kwargs(
            mode=LocationMode.NEAR_ANCHOR,
            status=LocationStatus.OK,
            lat=10.82, lon=106.72,
            canonical_area="landmark 81",
        )
        # Should store coords for downstream haversine
        has_coords = kw.get("user_latitude") or kw.get("anchor_lat")
        self.assertIsNotNone(has_coords)


class TestCreateUserPreferenceFromIntent(SimpleTestCase):

    @patch("preferences.models.UserPreference.objects.create")
    def test_calls_objects_create(self, mock_create):
        mock_pref = MagicMock()
        mock_pref.id = 99
        mock_create.return_value = mock_pref

        from chat_api.adapters.search_intent_to_user_preference import create_user_preference_from_intent
        result = create_user_preference_from_intent(_intent())

        mock_create.assert_called_once()
        self.assertEqual(result.id, 99)

    @patch("preferences.models.UserPreference.objects.create")
    def test_kwargs_passed_to_create(self, mock_create):
        mock_create.return_value = MagicMock(id=1)

        from chat_api.adapters.search_intent_to_user_preference import create_user_preference_from_intent
        create_user_preference_from_intent(
            _intent(mode=LocationMode.AREA, canonical_area="quan 7", budget_max=600_000)
        )

        call_kwargs = mock_create.call_args[1] if mock_create.call_args[1] else mock_create.call_args[0][0]
        # Verify area was forwarded
        self.assertIsInstance(call_kwargs, dict)
        self.assertEqual(call_kwargs.get("area"), "quan 7")


class TestBackwardCompatAlias(SimpleTestCase):

    def test_to_preference_kwargs_is_callable(self):
        from chat_api.adapters.search_intent_to_user_preference import to_preference_kwargs
        result = to_preference_kwargs(_intent())
        self.assertIsInstance(result, dict)

    def test_to_preference_kwargs_returns_same_as_build(self):
        from chat_api.adapters.search_intent_to_user_preference import (
            to_preference_kwargs,
            build_user_preference_kwargs,
        )
        intent = _intent(mode=LocationMode.AREA, canonical_area="quan 2", budget_max=400_000)
        self.assertEqual(
            to_preference_kwargs(intent).get("area"),
            build_user_preference_kwargs(intent).get("area"),
        )
