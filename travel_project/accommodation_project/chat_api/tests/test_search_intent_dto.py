"""
Unit tests for DTOs in chat_api/nlu/dto.py.
Run:  python manage.py test chat_api.tests.test_search_intent_dto
"""
from django.test import SimpleTestCase

from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)


class TestLocationModeEnum(SimpleTestCase):
    def test_all_modes_are_strings(self):
        for mode in LocationMode:
            self.assertIsInstance(mode.value, str)

    def test_known_modes_exist(self):
        expected = {
            "unknown", "anywhere", "area", "near_anchor",
            "near_user", "city_center", "hotel_name",
            "multiple_choice", "unsupported", "ambiguous",
        }
        self.assertEqual({m.value for m in LocationMode}, expected)

    def test_mode_from_string(self):
        self.assertEqual(LocationMode("area"), LocationMode.AREA)
        self.assertEqual(LocationMode("near_user"), LocationMode.NEAR_USER)
        self.assertEqual(LocationMode("hotel_name"), LocationMode.HOTEL_NAME)

    def test_mode_is_str_subclass(self):
        self.assertEqual(LocationMode.AREA, "area")


class TestLocationStatusEnum(SimpleTestCase):
    def test_known_statuses_exist(self):
        expected = {
            "ok", "unresolved", "unsupported", "conflict",
            "multiple_choice", "geocoded", "ambiguous", "none",
        }
        self.assertEqual({s.value for s in LocationStatus}, expected)

    def test_status_from_string(self):
        self.assertEqual(LocationStatus("ok"), LocationStatus.OK)
        self.assertEqual(LocationStatus("unresolved"), LocationStatus.UNRESOLVED)

    def test_status_is_str_subclass(self):
        self.assertEqual(LocationStatus.OK, "ok")


class TestResolvedLocation(SimpleTestCase):
    def test_defaults(self):
        loc = ResolvedLocation()
        self.assertEqual(loc.status, LocationStatus.NONE)
        self.assertEqual(loc.mode, LocationMode.UNKNOWN)
        self.assertIsNone(loc.canonical_area)
        self.assertIsNone(loc.latitude)
        self.assertIsNone(loc.longitude)
        self.assertEqual(loc.radius_km, 10.0)
        self.assertFalse(loc.cache_hit)
        self.assertIsInstance(loc.debug, dict)

    def test_can_set_all_fields(self):
        loc = ResolvedLocation(
            status=LocationStatus.OK,
            mode=LocationMode.AREA,
            canonical_area="quan 1",
            display_label="Quận 1",
            latitude=10.77,
            longitude=106.69,
            radius_km=5.0,
            provider="osm",
            cache_hit=True,
        )
        self.assertEqual(loc.canonical_area, "quan 1")
        self.assertAlmostEqual(loc.latitude, 10.77)
        self.assertTrue(loc.cache_hit)

    def test_debug_is_independent_per_instance(self):
        a = ResolvedLocation()
        b = ResolvedLocation()
        a.debug["key"] = "value"
        self.assertNotIn("key", b.debug)

    def test_anchor_fields(self):
        loc = ResolvedLocation(
            anchor_name="Landmark 81",
            anchor_kind="landmark",
            nearby_poi_key="cafe",
            nearby_poi_label="Quán cafe",
        )
        self.assertEqual(loc.anchor_name, "Landmark 81")
        self.assertEqual(loc.anchor_kind, "landmark")
        self.assertEqual(loc.nearby_poi_key, "cafe")


class TestUserLocationInput(SimpleTestCase):
    def test_required_fields(self):
        gps = UserLocationInput(lat=10.77, lon=106.69)
        self.assertAlmostEqual(gps.lat, 10.77)
        self.assertAlmostEqual(gps.lon, 106.69)
        self.assertIsNone(gps.accuracy)
        self.assertEqual(gps.radius_km, 10.0)

    def test_full_construction(self):
        gps = UserLocationInput(lat=10.0, lon=106.0, accuracy=15.0, radius_km=3.0)
        self.assertEqual(gps.accuracy, 15.0)
        self.assertEqual(gps.radius_km, 3.0)


class TestSearchIntent(SimpleTestCase):
    def test_defaults(self):
        intent = SearchIntent()
        self.assertEqual(intent.raw_text, "")
        self.assertEqual(intent.locale, "vi")
        self.assertEqual(intent.conversation_intent, "unknown")
        self.assertEqual(intent.input_kind, "text")
        self.assertIsNone(intent.area)
        self.assertIsNone(intent.hotel_name)
        self.assertIsNone(intent.budget)
        self.assertIsNone(intent.guest_count)
        self.assertIsNone(intent.trip_days)
        self.assertEqual(intent.accommodation_types, [])
        self.assertEqual(intent.required_amenities, [])
        self.assertEqual(intent.priorities, [])
        self.assertEqual(intent.confidence, 0.0)
        self.assertIsInstance(intent.location, ResolvedLocation)
        self.assertIsNone(intent.user_location)

    def test_location_is_independent_per_instance(self):
        a = SearchIntent()
        b = SearchIntent()
        a.location.canonical_area = "quan 1"
        self.assertIsNone(b.location.canonical_area)

    def test_lists_are_independent_per_instance(self):
        a = SearchIntent()
        b = SearchIntent()
        a.required_amenities.append("wifi")
        self.assertEqual(b.required_amenities, [])

    def test_full_construction(self):
        intent = SearchIntent(
            raw_text="gần Landmark 81",
            locale="vi",
            conversation_intent="search",
            input_kind="landmark_or_poi",
            area=None,
            hotel_name=None,
            accommodation_types=["hotel"],
            budget=500_000,
            budget_max=800_000,
            guest_count=2,
            trip_days=3,
            required_amenities=["wifi", "pool"],
            confidence=0.85,
        )
        self.assertEqual(intent.raw_text, "gần Landmark 81")
        self.assertEqual(intent.budget, 500_000)
        self.assertEqual(intent.guest_count, 2)
        self.assertIn("wifi", intent.required_amenities)
        self.assertAlmostEqual(intent.confidence, 0.85)
