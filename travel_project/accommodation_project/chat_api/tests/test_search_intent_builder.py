"""
Unit tests for SearchIntentBuilder.build().

Focused on the builder API and its interaction with the resolver.
Complements chat_api/nlu/test_search_intent_builder.py (46 lower-level tests).

Run:  python manage.py test chat_api.tests.test_search_intent_builder
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from chat_api.nlu.dto import LocationMode, LocationStatus, ResolvedLocation, UserLocationInput
from chat_api.nlu.search_intent_builder import SearchIntentBuilder

_MODULE = "chat_api.nlu.search_intent_builder"


def _ok_resolved(**kw) -> ResolvedLocation:
    return ResolvedLocation(
        status=LocationStatus.OK,
        mode=kw.get("mode", LocationMode.AREA),
        canonical_area=kw.get("canonical_area", "quan 1"),
        display_label=kw.get("display_label", "Quận 1"),
        latitude=kw.get("latitude", 10.77),
        longitude=kw.get("longitude", 106.69),
        radius_km=kw.get("radius_km", 5.0),
        provider="test",
        cache_hit=True,
    )


def _make_resolver_mock(resolved: ResolvedLocation) -> MagicMock:
    instance = MagicMock()
    instance.resolve.return_value = resolved
    cls_mock = MagicMock()
    cls_mock.default.return_value = instance
    return cls_mock


class TestBuilderAnywhere(SimpleTestCase):
    def setUp(self):
        self.builder = SearchIntentBuilder()

    def test_anywhere_mode(self):
        intent = self.builder.build("ở đâu cũng được")
        self.assertEqual(intent.location.mode, LocationMode.ANYWHERE)
        self.assertEqual(intent.location.status, LocationStatus.OK)

    def test_anywhere_display_label(self):
        intent = self.builder.build("ở đâu cũng được")
        self.assertEqual(intent.location.display_label, "Anywhere")

    def test_anywhere_with_budget(self):
        intent = self.builder.build("ở đâu cũng được 300k")
        self.assertEqual(intent.location.mode, LocationMode.ANYWHERE)
        self.assertEqual(intent.budget, 300_000)

    def test_anywhere_with_amenity(self):
        intent = self.builder.build("ở đâu cũng được có wifi")
        self.assertEqual(intent.location.mode, LocationMode.ANYWHERE)
        self.assertIn("wifi", intent.required_amenities)


class TestBuilderNearMe(SimpleTestCase):
    def setUp(self):
        self.builder = SearchIntentBuilder()

    def test_near_me_no_gps_unresolved(self):
        intent = self.builder.build("gần tôi", user_location=None)
        self.assertEqual(intent.location.status, LocationStatus.UNRESOLVED)
        self.assertEqual(intent.location.mode, LocationMode.NEAR_USER)

    def test_near_me_no_gps_needs_location_flag(self):
        intent = self.builder.build("gần tôi", user_location=None)
        self.assertTrue(intent.location.debug.get("needs_user_location"))

    def test_near_me_with_gps_ok(self):
        gps = UserLocationInput(lat=10.77, lon=106.69)
        intent = self.builder.build("gần tôi", user_location=gps)
        self.assertEqual(intent.location.mode, LocationMode.NEAR_USER)
        self.assertEqual(intent.location.status, LocationStatus.OK)
        self.assertAlmostEqual(intent.location.latitude, 10.77)

    def test_near_me_with_gps_provider(self):
        gps = UserLocationInput(lat=10.77, lon=106.69)
        intent = self.builder.build("gần tôi", user_location=gps)
        self.assertEqual(intent.location.provider, "browser_gps")


class TestBuilderSlotExtraction(SimpleTestCase):
    def setUp(self):
        self.builder = SearchIntentBuilder()

    def test_budget_k_unit(self):
        intent = self.builder.build("200k")
        self.assertEqual(intent.budget, 200_000)

    def test_budget_tr_unit(self):
        intent = self.builder.build("1tr")
        self.assertEqual(intent.budget, 1_000_000)

    def test_budget_decimal(self):
        intent = self.builder.build("2.5tr")
        self.assertEqual(intent.budget, 2_500_000)

    def test_guest_count_nguoi(self):
        intent = self.builder.build("3 người")
        self.assertEqual(intent.guest_count, 3)

    def test_guest_count_cap_doi(self):
        intent = self.builder.build("cặp đôi")
        self.assertEqual(intent.guest_count, 2)

    def test_trip_days(self):
        intent = self.builder.build("3 ngày")
        self.assertEqual(intent.trip_days, 3)

    def test_amenity_wifi(self):
        intent = self.builder.build("có wifi")
        self.assertIn("wifi", intent.required_amenities)

    def test_amenity_pool(self):
        intent = self.builder.build("có hồ bơi")
        self.assertIn("pool", intent.required_amenities)

    def test_amenity_parking(self):
        intent = self.builder.build("có parking")
        self.assertIn("parking", intent.required_amenities)

    def test_accommodation_type_homestay(self):
        intent = self.builder.build("tìm homestay")
        self.assertIn("homestay", intent.accommodation_types)

    def test_accommodation_type_hotel(self):
        intent = self.builder.build("khách sạn")
        self.assertIn("hotel", intent.accommodation_types)


class TestBuilderContextSlots(SimpleTestCase):
    def setUp(self):
        self.builder = SearchIntentBuilder()

    def test_context_budget_used_as_fallback(self):
        intent = self.builder.build("tìm homestay", context_slots={"budget": 500_000})
        self.assertEqual(intent.budget, 500_000)

    def test_text_budget_overrides_context(self):
        intent = self.builder.build("300k", context_slots={"budget": 100_000})
        self.assertEqual(intent.budget, 300_000)

    def test_context_guest_count_fallback(self):
        intent = self.builder.build("tìm phòng", context_slots={"guest_count": 4})
        self.assertEqual(intent.guest_count, 4)


class TestBuilderMetadata(SimpleTestCase):
    def setUp(self):
        self.builder = SearchIntentBuilder()

    def test_raw_text_preserved(self):
        text = "gần Landmark 81 ở quận 7"
        resolver_cls = _make_resolver_mock(_ok_resolved())
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build(text)
        self.assertEqual(intent.raw_text, text)

    def test_locale_default_vi(self):
        intent = self.builder.build("ở đâu cũng được")
        self.assertEqual(intent.locale, "vi")

    def test_locale_override(self):
        intent = self.builder.build("ở đâu cũng được", locale="en")
        self.assertEqual(intent.locale, "en")

    def test_selected_place_passed_through(self):
        resolver_cls = _make_resolver_mock(_ok_resolved())
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("ở đây", selected_place="Quận 1")
        self.assertEqual(intent.selected_place, "Quận 1")

    def test_debug_empty_by_default(self):
        intent = self.builder.build("ở đâu cũng được")
        self.assertEqual(intent.debug, {})

    def test_debug_populated_when_flag_set(self):
        intent = self.builder.build("ở đâu cũng được", include_debug=True)
        self.assertIn("classification", intent.debug)
        self.assertIn("is_anywhere", intent.debug)

    def test_confidence_positive(self):
        intent = self.builder.build("xin chào")
        self.assertGreater(intent.confidence, 0.0)


class TestBuilderEdgeCases(SimpleTestCase):
    def setUp(self):
        self.builder = SearchIntentBuilder()

    def test_empty_text_returns_intent(self):
        intent = self.builder.build("")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.input_kind, "unknown")

    def test_whitespace_only_returns_intent(self):
        intent = self.builder.build("   ")
        self.assertIsNotNone(intent)

    def test_never_raises_for_odd_inputs(self):
        for bad in [None, 123, [], {}, True]:
            try:
                self.builder.build(str(bad))
            except Exception as exc:
                self.fail(f"build() raised for {bad!r}: {exc}")

    def test_resolver_called_for_area_query(self):
        resolved = _ok_resolved(canonical_area="quan 3")
        resolver_cls = _make_resolver_mock(resolved)
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("tìm phòng ở quận 3")
        # Areas are canonicalized to display form (e.g. "quan 3" → "Quận 3")
        self.assertEqual(intent.location.canonical_area, "Quận 3")
        self.assertEqual(intent.area, "Quận 3")

    def test_unresolved_when_resolver_fails(self):
        resolver_cls = _make_resolver_mock(
            ResolvedLocation(status=LocationStatus.UNRESOLVED, mode=LocationMode.UNKNOWN)
        )
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("tìm phòng có wifi")
        self.assertEqual(intent.location.status, LocationStatus.UNRESOLVED)
